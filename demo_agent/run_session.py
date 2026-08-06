import argparse
import asyncio
import csv
import logging
from pathlib import Path

import yaml

from .agent import Agent
from .tools.file_reader import set_corpus_root

logger = logging.getLogger(__name__)


def _load_tasks(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, list) else data.get("tasks", [])


async def _run_sessions(
    gateway_url: str,
    tasks: list[dict],
    n_sessions: int,
    session_id_prefix: str,
    output_csv: Path | None,
) -> None:
    results = []
    agent = Agent(gateway_url)
    try:
        for i in range(n_sessions):
            task = tasks[i % len(tasks)]
            session_id = f"{session_id_prefix}-{i:04d}"
            result = await agent.run_task(task, session_id=session_id)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{status}] {result.task_id} session={session_id} "
                f"turns={result.turns} {result.elapsed_seconds:.1f}s"
            )
    finally:
        await agent.close()

    passed = sum(1 for r in results if r.passed)
    print(f"\nResults: {passed}/{len(results)} passed")

    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "task_id",
                    "session_id",
                    "passed",
                    "turns",
                    "elapsed_seconds",
                ],
            )
            writer.writeheader()
            for r in results:
                writer.writerow(r.model_dump(exclude={"answer"}))
        logger.info("wrote results to %s", output_csv)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run demo agent sessions against the gateway"
    )
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--sessions", type=int, default=5)
    parser.add_argument(
        "--task-file",
        type=Path,
        default=Path(__file__).parent / "tasks" / "tasks.yaml",
    )
    parser.add_argument("--session-id-prefix", default="demo")
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(__file__).parent / "corpus",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    set_corpus_root(args.corpus_dir)
    tasks = _load_tasks(args.task_file)

    asyncio.run(
        _run_sessions(
            args.gateway_url,
            tasks,
            args.sessions,
            args.session_id_prefix,
            args.output_csv,
        )
    )


if __name__ == "__main__":
    main()
