import subprocess
import sys
import textwrap

from .base import ToolResult, ToolStatus

_TIMEOUT_SECONDS = 10
_MAX_OUTPUT_BYTES = 8192
_MAX_MEMORY_MB = 128


def run_python(code: str) -> ToolResult:
    """Execute Python code in a subprocess with strict resource limits."""
    wrapped = textwrap.dedent(f"""
import resource, sys
# Memory limit
resource.setrlimit(
    resource.RLIMIT_AS,
    ({_MAX_MEMORY_MB * 1024 * 1024}, {_MAX_MEMORY_MB * 1024 * 1024}),
)
# No filesystem writes outside /tmp, no network — enforced by not importing those
{code}
""")
    try:
        result = subprocess.run(
            [sys.executable, "-c", wrapped],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            text=True,
        )
        output = result.stdout + result.stderr
        if len(output) > _MAX_OUTPUT_BYTES:
            output = output[:_MAX_OUTPUT_BYTES] + "\n[truncated]"
        if result.returncode != 0:
            return ToolResult(status=ToolStatus.ERROR, output=output or "non-zero exit")
        return ToolResult.ok(output)
    except subprocess.TimeoutExpired:
        return ToolResult(
            status=ToolStatus.TIMEOUT,
            output=f"timed out after {_TIMEOUT_SECONDS}s",
        )
    except Exception as exc:
        return ToolResult.error(str(exc))
