"""
Load study: saturation, affinity, routing, and failure drill.

Usage:
    python3 studies/run_study.py [--gateway-url URL] [--run-id ID] [--skip-drill]

Results are written to studies/results/<run-id>/ as CSV files and summary.json.
"""
import argparse
import asyncio
import csv
import json
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from loadgen.models import LoadMode, ProfileConfig, TurnSpec
from loadgen.generator import LoadGenerator

_SYS_BASE = (
    "You are a helpful research assistant with access to a local knowledge corpus. "
    "Answer factual questions accurately and concisely. "
)
SYSTEM_PROMPT_3KB = (_SYS_BASE * 50)[:3072]


def _pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = max(0, min(int(len(s) * p / 100), len(s) - 1))
    return s[idx]


def _read_csv_ok(path):
    if not Path(path).exists():
        return []
    return [r for r in csv.DictReader(open(path)) if r.get("status_code") == "200"]


def _summarise(label, rows):
    if not rows:
        print(f"  [{label}] no rows", flush=True)
        return {}
    e2e = [float(r["e2e_ms"]) for r in rows]
    hits = sum(1 for r in rows if r.get("affinity_hit") == "True")
    tiers = set(r.get("tier", "?") for r in rows)
    result = {
        "n": len(e2e),
        "tiers": sorted(tiers),
        "p50_ms": round(_pct(e2e, 50)),
        "p95_ms": round(_pct(e2e, 95)),
        "p99_ms": round(_pct(e2e, 99)),
        "affinity_hit_rate": round(hits / len(e2e), 3),
    }
    print(
        f"  [{label}] n={result['n']} tiers={tiers} "
        f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms p99={result['p99_ms']}ms "
        f"affinity_hit={hits}/{result['n']}={result['affinity_hit_rate']:.1%}",
        flush=True,
    )
    return result


async def study_saturation(gateway, results):
    print("\n=== Study 1: Small-tier saturation (REPS=3, 3KB prompt) ===", flush=True)
    REPS = 3
    sat = {}
    for c in [1, 4, 8, 16]:
        all_rows = []
        for rep in range(1, REPS + 1):
            p = ProfileConfig(
                name=f"sat_c{c}_r{rep}",
                description=f"saturation c={c} rep={rep}",
                mode=LoadMode.CLOSED_LOOP,
                concurrency=c,
                total_sessions=c * 4,
                think_time_seconds=0.0,
                tier_hint="small",
                turn_spec=TurnSpec(
                    min_turns=2, max_turns=2,
                    system_prompt_chars=3072,
                    user_prompt_chars=100,
                ),
            )
            await LoadGenerator(gateway, p).run(results / f"sat_c{c}_r{rep}.csv")
            rows = _read_csv_ok(results / f"sat_c{c}_r{rep}.csv")
            all_rows.extend(rows)
            print(f"  [sat] c={c} rep={rep}/{REPS} n={len(rows)}", flush=True)

        combined = results / f"sat_c{c}_combined.csv"
        if all_rows:
            with combined.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
                w.writeheader()
                w.writerows(all_rows)

        sat[c] = _summarise(f"sat c={c}", all_rows)
    return sat


async def study_affinity(gateway, results):
    print("\n=== Study 2: Affinity ON vs OFF (3KB prompt) ===", flush=True)

    p_on = ProfileConfig(
        name="affinity_on",
        description="affinity ON: 12 sessions x 6 turns",
        mode=LoadMode.CLOSED_LOOP,
        concurrency=6,
        total_sessions=12,
        think_time_seconds=0.0,
        tier_hint="small",
        turn_spec=TurnSpec(min_turns=6, max_turns=6, system_prompt_chars=3072, user_prompt_chars=100),
    )
    await LoadGenerator(gateway, p_on).run(results / "affinity_on.csv")
    rows_on = _read_csv_ok(results / "affinity_on.csv")
    sum_on = _summarise("affinity ON", rows_on)

    print("  [affinity] running OFF (72 single-turn sessions)...", flush=True)
    p_off = ProfileConfig(
        name="affinity_off",
        description="affinity OFF: 72 single-turn sessions, fresh IDs",
        mode=LoadMode.CLOSED_LOOP,
        concurrency=6,
        total_sessions=72,
        think_time_seconds=0.0,
        tier_hint="small",
        turn_spec=TurnSpec(min_turns=1, max_turns=1, system_prompt_chars=3072, user_prompt_chars=100),
    )
    await LoadGenerator(gateway, p_off).run(results / "affinity_off.csv")
    rows_off = _read_csv_ok(results / "affinity_off.csv")
    sum_off = _summarise("affinity OFF", rows_off)

    return {"on": sum_on, "off": sum_off}


async def study_routing(gateway, results):
    print("\n=== Study 3: Classifier routing (auto, short prompts) ===", flush=True)
    p = ProfileConfig(
        name="routing_auto",
        description="auto tier: classifier decides",
        mode=LoadMode.CLOSED_LOOP,
        concurrency=4,
        total_sessions=20,
        think_time_seconds=0.0,
        tier_hint="auto",
        turn_spec=TurnSpec(min_turns=1, max_turns=1, system_prompt_chars=300, user_prompt_chars=100),
    )
    await LoadGenerator(gateway, p).run(results / "routing_auto.csv")
    rows = _read_csv_ok(results / "routing_auto.csv")
    big = [r for r in rows if r.get("tier") == "big"]
    small = [r for r in rows if r.get("tier") == "small"]
    print(f"  [routing] total={len(rows)} big={len(big)} small={len(small)}", flush=True)
    return {"total": len(rows), "big": len(big), "small": len(small)}


async def study_failure_drill(gateway, results):
    print("\n=== Study 4: Failure drill (kill small-0) ===", flush=True)
    CONTAINER = "agent-serve-vllm-small-0-1"
    drill_rows = []
    fieldnames = ["phase", "req_idx", "status", "e2e_ms", "backend", "tier", "elapsed_since_kill_s"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        print("  [drill] baseline (20 requests)...", flush=True)
        baseline_e2e = []
        for i in range(20):
            t0 = time.monotonic()
            try:
                r = await client.post(
                    f"{gateway}/v1/chat/completions",
                    json={"model": "auto",
                          "messages": [{"role": "system", "content": "Be brief."},
                                       {"role": "user", "content": "What is 2+2?"}]},
                    headers={"X-Session-Id": f"drill-base-{i}", "X-Tier-Hint": "small"},
                )
                e2e = (time.monotonic() - t0) * 1000
                meta = r.json().get("x_agent_serve", {}) if r.status_code == 200 else {}
                baseline_e2e.append(e2e)
                drill_rows.append({"phase": "before_kill", "req_idx": i, "status": r.status_code,
                                   "e2e_ms": round(e2e), "backend": meta.get("backend_id", "?"),
                                   "tier": meta.get("tier", "?"), "elapsed_since_kill_s": ""})
            except Exception as exc:
                drill_rows.append({"phase": "before_kill", "req_idx": i, "status": 0,
                                   "e2e_ms": -1, "backend": "?", "tier": "?",
                                   "elapsed_since_kill_s": "", "error": str(exc)})

        if baseline_e2e:
            print(f"  [drill] baseline p50={statistics.median(baseline_e2e):.0f}ms n={len(baseline_e2e)}", flush=True)

        print(f"  [drill] stopping {CONTAINER}...", flush=True)
        kill_time = time.monotonic()
        subprocess.run(["docker", "stop", "-t", "1", CONTAINER], capture_output=True)

        print("  [drill] post-kill requests (40)...", flush=True)
        first_failover = None
        for i in range(40):
            t0 = time.monotonic()
            elapsed = t0 - kill_time
            try:
                r = await client.post(
                    f"{gateway}/v1/chat/completions",
                    json={"model": "auto",
                          "messages": [{"role": "system", "content": "Be brief."},
                                       {"role": "user", "content": "What is 3+3?"}]},
                    headers={"X-Session-Id": f"drill-post-{i}", "X-Tier-Hint": "small"},
                )
                e2e = (time.monotonic() - t0) * 1000
                meta = r.json().get("x_agent_serve", {}) if r.status_code == 200 else {}
                backend = meta.get("backend_id", "?")
                if backend == "small-1" and first_failover is None:
                    first_failover = i
                drill_rows.append({"phase": "after_kill", "req_idx": i, "status": r.status_code,
                                   "e2e_ms": round(e2e), "backend": backend,
                                   "tier": meta.get("tier", "?"),
                                   "elapsed_since_kill_s": round(elapsed, 1)})
                print(f"  [drill] req {i:2d} t+{elapsed:.0f}s -> {r.status_code} backend={backend}", flush=True)
            except Exception as exc:
                elapsed = time.monotonic() - kill_time
                drill_rows.append({"phase": "after_kill", "req_idx": i, "status": 0,
                                   "e2e_ms": -1, "backend": "?", "tier": "?",
                                   "elapsed_since_kill_s": round(elapsed, 1)})

    with (results / "failure_drill.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(drill_rows)

    print(f"  [drill] restarting {CONTAINER}...", flush=True)
    subprocess.run(["docker", "start", CONTAINER], capture_output=True)

    after = [r for r in drill_rows if r["phase"] == "after_kill"]
    ok = [r for r in after if r["status"] == 200]
    failed = [r for r in after if r["status"] != 200]
    return {
        "baseline_p50_ms": round(statistics.median(baseline_e2e)) if baseline_e2e else 0,
        "post_kill_ok": len(ok),
        "post_kill_failed": len(failed),
        "first_failover_req_idx": first_failover,
    }


async def main(gateway, results_dir, skip_drill):
    results_dir.mkdir(parents=True, exist_ok=True)
    print(f"[study] results -> {results_dir}", flush=True)

    sat = await study_saturation(gateway, results_dir)
    affinity = await study_affinity(gateway, results_dir)
    routing = await study_routing(gateway, results_dir)
    drill = await study_failure_drill(gateway, results_dir) if not skip_drill else {"skipped": True}

    summary = {
        "run_id": results_dir.name,
        "saturation": sat,
        "affinity": affinity,
        "routing": routing,
        "failure_drill": drill,
    }
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[study] complete -- summary.json written", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="agent-serve load study")
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--skip-drill", action="store_true", help="Skip the failure drill (avoids killing a container)")
    args = parser.parse_args()

    results_path = Path(__file__).parent / "results" / args.run_id
    asyncio.run(main(args.gateway_url, results_path, args.skip_drill))
