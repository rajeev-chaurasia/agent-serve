import argparse
import asyncio
import csv
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def replay(csv_path: Path, gateway_url: str, concurrency: int, speed: float = 1.0) -> None:
    """Replay a recorded load CSV against the gateway.

    Args:
        csv_path: path to a CSV produced by generator.py
        gateway_url: gateway base URL
        concurrency: max concurrent in-flight requests
        speed: replay speed multiplier (2.0 = twice as fast)
    """
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    logger.info("replaying %d rows at concurrency=%d speed=%.1fx", len(rows), concurrency, speed)
    semaphore = asyncio.Semaphore(concurrency)

    async def replay_one(row: dict) -> None:
        async with semaphore:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": "auto",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"Replay request {row['request_id']}"},
                    ],
                }
                headers = {
                    "X-Session-Id": row["session_id"],
                    "X-Agent-Id": row["agent_id"],
                    "X-Tier-Hint": row.get("tier", "auto"),
                }
                try:
                    r = await client.post(f"{gateway_url}/v1/chat/completions", json=payload, headers=headers)
                    logger.debug("replayed %s -> %d", row["request_id"], r.status_code)
                except Exception as exc:
                    logger.warning("replay failed for %s: %s", row["request_id"], exc)

    tasks = [asyncio.create_task(replay_one(row)) for row in rows]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("replay complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a recorded load trace")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(replay(args.csv, args.gateway_url, args.concurrency, args.speed))
