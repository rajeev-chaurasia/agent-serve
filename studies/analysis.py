#!/usr/bin/env python3
"""
Load study analysis — reads CSVs from a results directory, produces PNG plots.
"""
import argparse
import csv
import json
import logging
from pathlib import Path
import statistics

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available — skipping plots")


def _read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _p50(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.median(values)


def _p99(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * 0.99)
    return s[min(idx, len(s) - 1)]


def plot_saturation(results_dir: Path, output_dir: Path) -> None:
    """Plot p50/p99 TTFT and E2E vs concurrency level."""
    concurrencies = []
    p50_ttft = []
    p99_ttft = []
    p50_e2e = []
    p99_e2e = []

    for c in sorted([1, 2, 4, 8, 16, 24, 32]):
        rows = []
        for f in results_dir.glob(f"sat_c{c}_r*.csv"):
            rows.extend(_read_csv(f))
        if not rows:
            continue
        ok = [r for r in rows if r.get("status_code") == "200"]
        if not ok:
            continue
        ttft = [float(r["ttft_ms"]) for r in ok]
        e2e = [float(r["e2e_ms"]) for r in ok]
        concurrencies.append(c)
        p50_ttft.append(_p50(ttft))
        p99_ttft.append(_p99(ttft))
        p50_e2e.append(_p50(e2e))
        p99_e2e.append(_p99(e2e))

    if not concurrencies or not HAS_MATPLOTLIB:
        logger.info("saturation data not available or matplotlib missing — skipping plot")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(concurrencies, p50_ttft, "o-", label="p50", color="#2196F3")
    ax1.plot(concurrencies, p99_ttft, "s--", label="p99", color="#F44336")
    ax1.set_xlabel("Concurrent Sessions")
    ax1.set_ylabel("TTFT (ms)")
    ax1.set_title("TTFT vs Concurrency")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(concurrencies, p50_e2e, "o-", label="p50", color="#4CAF50")
    ax2.plot(concurrencies, p99_e2e, "s--", label="p99", color="#FF9800")
    ax2.set_xlabel("Concurrent Sessions")
    ax2.set_ylabel("E2E Latency (ms)")
    ax2.set_title("E2E Latency vs Concurrency")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    out = output_dir / "saturation.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", out)


def plot_affinity(results_dir: Path, output_dir: Path) -> None:
    """Bar chart: affinity ON vs OFF — p50 TTFT per turn depth."""
    on_rows, off_rows = [], []
    for f in results_dir.glob("affinity_on*.csv"):
        on_rows.extend(_read_csv(f))
    for f in results_dir.glob("affinity_off*.csv"):
        off_rows.extend(_read_csv(f))

    if not on_rows or not HAS_MATPLOTLIB:
        logger.info("affinity data not available — skipping plot")
        return

    def avg_e2e(rows):
        vals = [float(r["e2e_ms"]) for r in rows if r.get("status_code") == "200"]
        return _p50(vals) if vals else 0.0

    labels = ["Affinity ON"]
    values = [avg_e2e(on_rows)]
    colors = ["#2196F3"]
    if off_rows:
        labels.append("Affinity OFF")
        values.append(avg_e2e(off_rows))
        colors.append("#F44336")

    fig, ax = plt.subplots(figsize=(6, 5))
    bars = ax.bar(labels, values, color=colors, width=0.4)
    ax.bar_label(bars, fmt="%.0f ms")
    ax.set_ylabel("Median E2E Latency (ms)")
    ax.set_title("Session-Affinity Impact on E2E Latency")
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    out = output_dir / "affinity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", out)


def plot_routing_economics(results_dir: Path, output_dir: Path) -> None:
    """Table + pie chart: small vs big tier distribution from mixed profile."""
    rows = []
    for f in results_dir.glob("mixed_r*.csv"):
        rows.extend(_read_csv(f))

    if not rows or not HAS_MATPLOTLIB:
        logger.info("mixed profile data not available — skipping economics plot")
        return

    ok = [r for r in rows if r.get("status_code") == "200"]
    small = [r for r in ok if r.get("tier") == "small"]
    big = [r for r in ok if r.get("tier") == "big"]

    fig, ax = plt.subplots(figsize=(6, 5))
    sizes = [len(small), len(big)]
    labels = [f"Small tier\n{len(small)} req", f"Big tier\n{len(big)} req"]
    ax.pie(sizes, labels=labels, colors=["#4CAF50", "#FF9800"], autopct="%1.0f%%", startangle=90)
    ax.set_title("Request Distribution by Tier (mixed profile)")

    fig.tight_layout()
    out = output_dir / "routing_economics.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", out)


def generate_synthetic_data(results_dir: Path) -> None:
    """Generate minimal synthetic CSVs for testing the analysis pipeline."""
    import random
    random.seed(42)

    # Saturation synthetic
    for c in [1, 4, 8, 16]:
        rows = []
        for _ in range(c * 3):
            rows.append({
                "request_id": "r1", "session_id": "s1", "agent_id": "a1",
                "tier": "small", "backend_id": "small-0",
                "ttft_ms": str(random.gauss(80 + c * 5, 20)),
                "e2e_ms": str(random.gauss(200 + c * 15, 50)),
                "input_tokens": "100", "output_tokens": "50",
                "affinity_hit": "True", "status_code": "200",
                "timestamp_iso": "2024-01-01T00:00:00Z", "profile": "saturation",
            })
        p = results_dir / f"sat_c{c}_r1.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Affinity ON synthetic
    rows = [
        {"request_id": "r1", "session_id": f"s{i}", "agent_id": "a1",
         "tier": "small", "backend_id": "small-0", "ttft_ms": str(70 + i % 20),
         "e2e_ms": str(150 + i % 30), "input_tokens": "200", "output_tokens": "100",
         "affinity_hit": "True", "status_code": "200",
         "timestamp_iso": "2024-01-01T00:00:00Z", "profile": "deep_sessions"}
        for i in range(50)
    ]
    p = results_dir / "affinity_on_r1.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Mixed profile synthetic
    rows = []
    for i in range(100):
        tier = "small" if i % 3 != 0 else "big"
        rows.append({
            "request_id": f"r{i}", "session_id": f"s{i}", "agent_id": "a1",
            "tier": tier, "backend_id": f"{tier}-0",
            "ttft_ms": "80" if tier == "small" else "200",
            "e2e_ms": "200" if tier == "small" else "500",
            "input_tokens": "150", "output_tokens": "75",
            "affinity_hit": "True", "status_code": "200",
            "timestamp_iso": "2024-01-01T00:00:00Z", "profile": "mixed",
        })
    p = results_dir / "mixed_r1.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    logger.info("generated synthetic data in %s", results_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate load study plots from CSV results")
    parser.add_argument("--results-dir", type=Path, required=False, default=None)
    parser.add_argument("--run-id", type=str, default="latest")
    parser.add_argument("--synthetic", action="store_true", help="Generate and plot synthetic test data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.synthetic:
        results_dir = Path("studies/results/synthetic")
        generate_synthetic_data(results_dir)
    else:
        results_dir = args.results_dir or Path(f"studies/results/{args.run_id}")

    results_dir.mkdir(parents=True, exist_ok=True)
    plot_saturation(results_dir, results_dir)
    plot_affinity(results_dir, results_dir)
    plot_routing_economics(results_dir, results_dir)
    logger.info("analysis complete")


if __name__ == "__main__":
    main()
