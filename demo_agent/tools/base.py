from pydantic import BaseModel
from enum import Enum


class ToolStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    SANDBOX_VIOLATION = "sandbox_violation"


class ToolResult(BaseModel):
    status: ToolStatus
    output: str
    truncated: bool = False

    @classmethod
    def ok(cls, output: str, max_chars: int = 4000) -> "ToolResult":
        truncated = len(output) > max_chars
        return cls(status=ToolStatus.OK, output=output[:max_chars], truncated=truncated)

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        return cls(status=ToolStatus.ERROR, output=message)
