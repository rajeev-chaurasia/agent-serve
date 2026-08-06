import json
import asyncio
import logging
import time
from pathlib import Path

from .accountant import TokenAccountant

logger = logging.getLogger(__name__)


class SnapshotManager:
    """Periodically serializes accountant state to disk so budgets survive gateway restarts.

    The snapshot is best-effort — on restore we reconstruct approximate window state
    using stored (timestamp, tokens) entries, discarding anything older than the window.
    """

    def __init__(
        self,
        accountant: TokenAccountant,
        path: Path,
        interval_seconds: int = 60,
    ) -> None:
        self._accountant = accountant
        self._path = path
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="snapshot-loop")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._save()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            self._save()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                agent_id: {
                    "entries": state._entries,
                    "budget": state.budget,
                    "window_seconds": state.window_seconds,
                }
                for agent_id, state in self._accountant._states.items()
            }
            self._path.write_text(json.dumps(snapshot))
        except Exception:
            logger.exception("failed to save accounting snapshot to %s", self._path)

    def restore(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            now = time.monotonic()
            for agent_id, saved in data.items():
                state = self._accountant._states[agent_id]
                cutoff = now - saved["window_seconds"]
                state._entries = [
                    (ts, tokens)
                    for ts, tokens in saved["entries"]
                    if ts >= cutoff
                ]
            logger.info(
                "restored accounting snapshot from %s (%d agents)", self._path, len(data)
            )
        except Exception:
            logger.exception("failed to restore accounting snapshot, starting fresh")
