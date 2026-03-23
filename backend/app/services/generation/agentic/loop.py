"""Minimal agentic loop for generation jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.generation.agentic.context import (
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_KEEP_RECENT,
    attach_state_summary,
    compact_context,
    summarize_state,
)
from app.services.generation.agentic.pydantic_ai_adapter import PydanticAIModelClient
from app.services.generation.agentic.todo import TodoManager, build_todo_nag
from app.services.generation.agentic.tools import ToolDispatchResult
from app.services.generation.agentic.types import (
    AgenticMessage,
    AgenticModelClient,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)
from app.services.pipeline.graph import PipelineState

InstructionsProvider = str | Callable[[], str]
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
    state: PipelineState | None = None,
    todo_manager: TodoManager | None = None,
    tool_definitions: Sequence[dict] | None = None,
    dispatch_tools: ToolDispatcher | None = None,
    max_turns: int | None = None,
    compact_every_turns: int = 5,
    compact_max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS,
    compact_keep_recent: int = DEFAULT_KEEP_RECENT,
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
        last_response = await client.complete(
            _messages_for_model(messages, instructions=instructions, todo_manager=todo_manager),
            list(tool_definitions or []),
        )
        messages.append(last_response)

        tool_calls = [part for part in last_response.parts if isinstance(part, ToolCall)]
        if not tool_calls or dispatch_tools is None:
            messages = _maybe_compact_messages(
                messages,
                completed_turns=turn + 1,
                compact_every_turns=compact_every_turns,
                compact_max_tokens=compact_max_tokens,
                compact_keep_recent=compact_keep_recent,
                state=state,
            )
            return AgenticLoopResult(
                output_text=extract_text(last_response),
                messages=messages,
                turns=turn + 1,
                stop_reason="text" if not tool_calls else "tool-call-without-dispatch",
                last_response=last_response,
            )

        dispatch_result = await dispatch_tools(tool_calls)
        if dispatch_result.parts:
            messages.append(
                UserMessage(
                    parts=_attach_state_to_results(dispatch_result.parts, state),
                    instructions=_instructions(instructions),
                )
            )
        messages = _maybe_compact_messages(
            messages,
            completed_turns=turn + 1,
            compact_every_turns=compact_every_turns,
            compact_max_tokens=compact_max_tokens,
            compact_keep_recent=compact_keep_recent,
            state=state,
        )
        if dispatch_result.stop_loop:
            return AgenticLoopResult(
                output_text=extract_text(last_response),
                messages=messages,
                turns=turn + 1,
                stop_reason=dispatch_result.stop_reason or "tool-dispatch-stop",
                last_response=last_response,
            )

    messages.append(
        UserMessage(
            parts=["You have reached the maximum number of turns. Summarize the current progress briefly and stop."],
            instructions=_instructions(instructions),
        )
    )
    last_response = await client.complete(
        _messages_for_model(messages, instructions=instructions, todo_manager=todo_manager),
        list(tool_definitions or []),
    )
    messages.append(last_response)
    messages = _maybe_compact_messages(
        messages,
        completed_turns=turn_limit,
        compact_every_turns=compact_every_turns,
        compact_max_tokens=compact_max_tokens,
        compact_keep_recent=compact_keep_recent,
        state=state,
    )
    return AgenticLoopResult(
        output_text=extract_text(last_response),
        messages=messages,
        turns=turn_limit,
        max_turns_reached=True,
        stop_reason="max-turns",
        last_response=last_response,
    )


def _attach_state_to_results(
    parts: Sequence[ToolResult],
    state: PipelineState | None,
) -> list[str | ToolResult]:
    if state is None:
        return list(parts)
    return [attach_state_summary(part, state) for part in parts]


def _maybe_compact_messages(
    messages: list[AgenticMessage],
    *,
    completed_turns: int,
    compact_every_turns: int,
    compact_max_tokens: int,
    compact_keep_recent: int,
    state: PipelineState | None,
) -> list[AgenticMessage]:
    if compact_every_turns <= 0 or completed_turns % compact_every_turns != 0:
        return messages

    return compact_context(
        messages,
        max_tokens=compact_max_tokens,
        keep_recent=compact_keep_recent,
        state_summary=summarize_state(state) if state is not None else None,
    )


def _messages_for_model(
    messages: Sequence[AgenticMessage],
    *,
    instructions: InstructionsProvider | None,
    todo_manager: TodoManager | None,
) -> list[AgenticMessage]:
    prepared = list(messages)
    if todo_manager is None:
        return prepared

    nag = build_todo_nag(todo_manager)
    if not nag:
        return prepared

    prepared.append(UserMessage(parts=[nag], instructions=_instructions(instructions)))
    return prepared
