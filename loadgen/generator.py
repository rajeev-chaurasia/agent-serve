import asyncio
import csv
import hashlib
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from .models import LoadMode, ProfileConfig, ResultRow, TurnSpec

logger = logging.getLogger(__name__)

_SHARED_SYSTEM_PROMPT_BASE = "You are a helpful assistant. " + "Analyze the following carefully. " * 50


def _make_system_prompt(chars: int) -> str:
    base = _SHARED_SYSTEM_PROMPT_BASE
    return (base * ((chars // len(base)) + 1))[:chars]


def _make_user_prompt(chars: int, turn: int) -> str:
    templates = [
        "Explain the concept of caching in distributed systems.",
        "What are the tradeoffs between consistency and availability?",
        "Summarize what you know about gradient descent.",
        "How does prefix caching work in LLM serving?",
        "What is the difference between TCP and UDP?",
        "Describe a good approach for load testing an API.",
        "What is rendezvous hashing and when should you use it?",
        "Explain the sliding window algorithm for rate limiting.",
    ]
    base = templates[turn % len(templates)]
    return (base + " " + "Provide a detailed explanation. " * 10)[:chars]


class SessionRunner:
    """Runs a single multi-turn session against the gateway."""

    def __init__(self, client: httpx.AsyncClient, gateway_url: str, profile: ProfileConfig) -> None:
        self._client = client
        self._gateway_url = gateway_url
        self._profile = profile

    async def run(self, session_id: str) -> list[ResultRow]:
        spec = self._profile.turn_spec
        n_turns = random.randint(spec.min_turns, spec.max_turns)
        system_prompt = _make_system_prompt(spec.system_prompt_chars)
        rows = []

        for turn in range(n_turns):
            row = await self._single_turn(session_id, turn, system_prompt, spec)
            rows.append(row)
            if self._profile.think_time_seconds > 0:
                await asyncio.sleep(self._profile.think_time_seconds)
        return rows

    async def _single_turn(
        self, session_id: str, turn: int, system_prompt: str, spec: TurnSpec
    ) -> ResultRow:
        request_id = str(uuid.uuid4())
        user_content = _make_user_prompt(spec.user_prompt_chars, turn)
        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
        }
        headers = {
            "X-Session-Id": session_id,
            "X-Agent-Id": "loadgen",
            "X-Tier-Hint": self._profile.tier_hint,
        }

        t0 = time.monotonic()
        tier = "unknown"
        backend_id = "unknown"
        affinity_hit = False
        ttft_ms = 0.0
        input_tokens = 0
        output_tokens = 0
        status_code = 0

        try:
            r = await self._client.post(
                f"{self._gateway_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            status_code = r.status_code
            e2e_ms = (time.monotonic() - t0) * 1000
            ttft_ms = e2e_ms  # for non-streaming, TTFT == E2E
            if r.status_code == 200:
                data = r.json()
                meta = data.get("x_agent_serve", {})
                tier = meta.get("tier", "unknown")
                backend_id = meta.get("backend_id", "unknown")
                affinity_hit = meta.get("affinity_hit", False)
                ttft_ms = meta.get("queue_wait_ms", ttft_ms)
                usage = data.get("usage") or {}
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
        except Exception as exc:
            logger.warning("request failed session=%s turn=%d: %s", session_id, turn, exc)
            e2e_ms = (time.monotonic() - t0) * 1000
            status_code = 0

        return ResultRow(
            request_id=request_id,
            session_id=session_id,
            agent_id="loadgen",
            tier=tier,
            backend_id=backend_id,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            affinity_hit=affinity_hit,
            status_code=status_code,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            profile=self._profile.name,
        )


class LoadGenerator:
    """Drives concurrent session runners according to a profile.

    open_loop: spawns sessions at a fixed RPS (arrival rate independent of completion).
    closed_loop: maintains a fixed pool of concurrent sessions.
    """

    def __init__(self, gateway_url: str, profile: ProfileConfig) -> None:
        self._gateway_url = gateway_url
        self._profile = profile

    async def run(self, output_path: Path) -> list[ResultRow]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows: list[ResultRow] = []

        async with httpx.AsyncClient(timeout=300.0) as client:
            if self._profile.mode == LoadMode.CLOSED_LOOP:
                rows = await self._closed_loop(client)
            else:
                rows = await self._open_loop(client)

        self._write_csv(rows, output_path)
        logger.info("wrote %d rows to %s", len(rows), output_path)
        return rows

    async def _closed_loop(self, client: httpx.AsyncClient) -> list[ResultRow]:
        semaphore = asyncio.Semaphore(self._profile.concurrency)
        all_rows: list[ResultRow] = []
        lock = asyncio.Lock()

        async def run_one(idx: int) -> None:
            async with semaphore:
                session_id = f"loadgen-{self._profile.name}-{idx:05d}"
                runner = SessionRunner(client, self._gateway_url, self._profile)
                result = await runner.run(session_id)
                async with lock:
                    all_rows.extend(result)

        tasks = [asyncio.create_task(run_one(i)) for i in range(self._profile.total_sessions)]
        await asyncio.gather(*tasks, return_exceptions=True)
        return all_rows

    async def _open_loop(self, client: httpx.AsyncClient) -> list[ResultRow]:
        interval = 1.0 / self._profile.target_rps
        all_rows: list[ResultRow] = []
        lock = asyncio.Lock()
        pending = []

        async def run_one(idx: int) -> None:
            session_id = f"loadgen-ol-{self._profile.name}-{idx:05d}"
            runner = SessionRunner(client, self._gateway_url, self._profile)
            result = await runner.run(session_id)
            async with lock:
                all_rows.extend(result)

        for i in range(self._profile.total_sessions):
            t = asyncio.create_task(run_one(i))
            pending.append(t)
            await asyncio.sleep(interval)

        await asyncio.gather(*pending, return_exceptions=True)
        return all_rows

    def _write_csv(self, rows: list[ResultRow], path: Path) -> None:
        if not rows:
            return
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(ResultRow.model_fields.keys()))
            writer.writeheader()
            writer.writerows(r.model_dump() for r in rows)


def load_profile(path: Path) -> ProfileConfig:
    data = yaml.safe_load(path.read_text())
    return ProfileConfig(**data)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run agentic load generation against the gateway")
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--profile", type=Path, required=True, help="Path to profile YAML")
    parser.add_argument("--output", type=Path, default=Path("studies/results/loadgen.csv"))
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    profile = load_profile(args.profile)
    gen = LoadGenerator(args.gateway_url, profile)
    asyncio.run(gen.run(args.output))
