from . import file_reader
from .base import ToolResult


def search_corpus(query: str, max_results: int = 20) -> ToolResult:
    """Search corpus files for lines matching the query string."""
    if file_reader._CORPUS_ROOT is None:
        return ToolResult.error("corpus root not configured")
    _CORPUS_ROOT = file_reader._CORPUS_ROOT
    results = []
    for f in sorted(_CORPUS_ROOT.rglob("*")):
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(
                f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if query.lower() in line.lower():
                    rel = f.relative_to(_CORPUS_ROOT)
                    results.append(f"{rel}:{i}: {line.rstrip()}")
                    if len(results) >= max_results:
                        return ToolResult.ok("\n".join(results), max_chars=4000)
        except Exception:
            continue
    if not results:
        return ToolResult.error(f"no matches for: {query}")
    return ToolResult.ok("\n".join(results))
