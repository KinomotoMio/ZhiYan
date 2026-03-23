"""Minimal agentic loop for generation jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.generation.agentic.pydantic_ai_adapter import PydanticAIModelClient
from app.services.generation.agentic.types import (
    AgenticMessage,
    AgenticModelClient,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)

InstructionsProvider = str | Callable[[], str]
ToolDispatchResult = list[ToolResult]
ToolDispatcher = Callable[[Sequence[ToolCall]], Awaitable[ToolDispatchResult]]


@dataclass(slots=True)
class AgenticLoopResult:
    """Loop execution result."""

    output_text: str
    messages: list[AgenticMessage] = field(default_factory=list)
    turns: int = 0
    max_turns_reached: bool = False
    stop_reason: str = "text"
    last_response: AssistantMessage | None = None


def build_model(model_name=None) -> AgenticModelClient:
    """Build the default model client through a thin adapter."""

    return PydanticAIModelClient(model_name)


def extract_text(response: AssistantMessage | None) -> str:
    """Flatten plain text response parts."""

    if response is None:
        return ""

    parts = [part for part in response.parts if isinstance(part, str) and part]
    return "\n".join(parts).strip()


def _instructions(value: InstructionsProvider | None) -> str | None:
    if value is None:
        return None
    return value() if callable(value) else value


async def agentic_loop(
    user_prompt: str | None = None,
    *,
    model: AgenticModelClient | None = None,
    instructions: InstructionsProvider | None = None,
    message_history: Sequence[AgenticMessage] | None = None,
    tool_definitions: Sequence[dict] | None = None,
    dispatch_tools: ToolDispatcher | None = None,
    max_turns: int | None = None,
) -> AgenticLoopResult:
    """Run a simple `tool-call -> tool-result -> next turn` loop."""

    messages = list(message_history or [])
    if user_prompt:
        messages.append(UserMessage(parts=[user_prompt], instructions=_instructions(instructions)))
    elif not messages:
        raise ValueError("agentic_loop requires a user prompt or existing message history")

    client = model or build_model()
    turn_limit = max_turns or settings.agentic_max_turns
    last_response: AssistantMessage | None = None

    for turn in range(turn_limit):
        last_response = await client.complete(messages, list(tool_definitions or []))
        messages.append(last_response)

        tool_calls = [part for part in last_response.parts if isinstance(part, ToolCall)]
        if not tool_calls or dispatch_tools is None:
            return AgenticLoopResult(
                output_text=extract_text(last_response),
                messages=messages,
                turns=turn + 1,
                stop_reason="text" if not tool_calls else "tool-call-without-dispatch",
                last_response=last_response,
            )

        tool_results = await dispatch_tools(tool_calls)
        if tool_results:
            messages.append(UserMessage(parts=list(tool_results), instructions=_instructions(instructions)))

    messages.append(
        UserMessage(
            parts=["You have reached the maximum number of turns. Summarize the current progress briefly and stop."],
            instructions=_instructions(instructions),
        )
    )
    last_response = await client.complete(messages, list(tool_definitions or []))
    messages.append(last_response)
    return AgenticLoopResult(
        output_text=extract_text(last_response),
        messages=messages,
        turns=turn_limit,
        max_turns_reached=True,
        stop_reason="max-turns",
        last_response=last_response,
    )
