from pathlib import Path

from .base import ToolResult, ToolStatus

_CORPUS_ROOT: Path | None = None


def set_corpus_root(path: Path) -> None:
    global _CORPUS_ROOT
    _CORPUS_ROOT = path.resolve()


def read_file(path: str) -> ToolResult:
    """Read a file from the corpus directory. Rejects paths outside the corpus."""
    if _CORPUS_ROOT is None:
        return ToolResult.error("corpus root not configured")
    try:
        target = (_CORPUS_ROOT / path).resolve()
        if not str(target).startswith(str(_CORPUS_ROOT)):
            return ToolResult(
                status=ToolStatus.SANDBOX_VIOLATION,
                output=f"path escapes corpus root: {path}",
            )
        if not target.exists():
            return ToolResult.error(f"file not found: {path}")
        return ToolResult.ok(target.read_text(encoding="utf-8"))
    except Exception as exc:
        return ToolResult.error(str(exc))
