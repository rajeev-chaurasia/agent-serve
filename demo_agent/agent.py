import json
import logging
import time
import uuid
from typing import Any

import httpx
from pydantic import BaseModel

from .tools.base import ToolResult
from .tools.calculator import calculator
from .tools.corpus_search import search_corpus
from .tools.file_reader import read_file
from .tools.python_runner import run_python

logger = logging.getLogger(__name__)

# 3KB system prompt — intentionally long so prefix caching matters across sessions.
SYSTEM_PROMPT = """You are a helpful research assistant with access to a local knowledge corpus.
You can read files, search the corpus, run Python code, and perform calculations.
Always use the available tools to ground your answers in the corpus before responding.
Be precise, cite the specific file and line when referencing corpus content.
For calculations, always use the calculator tool rather than computing mentally.
For code questions, read the relevant file first, then explain step by step.
Think through multi-step problems systematically: identify what information you need,
gather it using tools, then synthesize a complete answer.
When searching, try multiple queries if the first doesn't return useful results.
Always provide a clear, complete answer after using the tools — don't just summarize tool output.
Available tools: read_file, search_corpus, run_python, calculator.
Constraints: maximum 8 tool calls per session, keep answers focused and under 500 words.
""" + (
    "Context: " + "A" * 2000
)  # pad to ~3KB for realistic prefix-cache testing


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the knowledge corpus",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within corpus",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_corpus",
            "description": "Search corpus files for lines matching a query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run Python code in a sandboxed subprocess",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a numeric arithmetic expression",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]

_TOOL_MAP: dict[str, Any] = {
    "read_file": lambda args: read_file(args["path"]),
    "search_corpus": lambda args: search_corpus(
        args["query"], args.get("max_results", 20)
    ),
    "run_python": lambda args: run_python(args["code"]),
    "calculator": lambda args: calculator(args["expression"]),
}


class TaskResult(BaseModel):
    task_id: str
    session_id: str
    passed: bool
    turns: int
    elapsed_seconds: float
    answer: str


class Agent:
    def __init__(self, gateway_url: str, model: str = "auto") -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def run_task(
        self, task: dict, session_id: str | None = None
    ) -> TaskResult:
        session_id = session_id or str(uuid.uuid4())
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": task["prompt"]})
        start = time.monotonic()
        final_answer = ""

        for _turn in range(8):  # cap at 8 agentic turns
            response = await self._call(
                messages, session_id, task.get("tier_hint", "auto")
            )
            choice = response["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls or choice.get("finish_reason") == "stop":
                final_answer = msg.get("content") or ""
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                handler = _TOOL_MAP.get(fn_name)
                if handler:
                    result: ToolResult = handler(fn_args)
                    tool_output = result.output
                else:
                    tool_output = f"unknown tool: {fn_name}"
                    logger.warning("agent called unknown tool %r", fn_name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_output,
                    }
                )

        keywords = task.get("expected_keywords", [])
        passed = all(kw.lower() in final_answer.lower() for kw in keywords)
        return TaskResult(
            task_id=task["id"],
            session_id=session_id,
            passed=passed,
            turns=sum(1 for m in messages if m["role"] == "assistant"),
            elapsed_seconds=time.monotonic() - start,
            answer=final_answer[:500],
        )

    async def _call(
        self, messages: list[dict], session_id: str, tier_hint: str
    ) -> dict:
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
        }
        r = await self._client.post(
            f"{self._gateway_url}/v1/chat/completions",
            json=payload,
            headers={
                "X-Session-Id": session_id,
                "X-Agent-Id": "demo-agent",
                "X-Tier-Hint": tier_hint,
            },
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._client.aclose()
