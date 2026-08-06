from pydantic import BaseModel, ConfigDict, Field

from .enums import Tier
from .models import TokenUsage


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list | None = None
    tool_choice: str | dict | None = None

    # Extra fields for gateway routing (not sent to backend)
    session_id: str | None = Field(None, alias="x_session_id")
    agent_id: str | None = Field(None, alias="x_agent_id")
    tier_hint: Tier = Field(Tier.AUTO, alias="x_tier_hint")

    model_config = ConfigDict(populate_by_name=True)


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: TokenUsage | None = None


class StreamDelta(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int
    delta: StreamDelta
    finish_reason: str | None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[StreamChoice]
