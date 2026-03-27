from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from litellm import acompletion

from app.core.model_status import split_model_identifier

from .types import AssistantMessage, Message, ToolCall, ToolMessage


@dataclass(slots=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class ModelResponse:
    message: AssistantMessage
    usage: ModelUsage = field(default_factory=ModelUsage)
    raw: Any | None = None


class ModelClient(Protocol):
    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        ...


@dataclass(slots=True)
class LiteLLMModelClient:
    model: str
    temperature: float | None = None
    api_base: str | None = None
    api_key: str | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        request: dict[str, Any] = {
            "model": normalize_litellm_model(self.model),
            "messages": _to_litellm_messages(messages),
        }
        if tools:
            request["tools"] = [_to_openai_tool(tool) for tool in tools]
            request["tool_choice"] = "auto"
        if self.temperature is not None:
            request["temperature"] = self.temperature
        if self.api_base is not None:
            request["api_base"] = self.api_base
        if self.api_key is not None:
            request["api_key"] = self.api_key
        request.update(self.extra_kwargs)

        response = await acompletion(**request)
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        for item in cast(list[Any], getattr(message, "tool_calls", None) or []):
            function = item.function
            raw_args = function.arguments
            if isinstance(raw_args, str):
                import json

                args = cast(dict[str, Any], json.loads(raw_args or "{}"))
            else:
                args = cast(dict[str, Any], raw_args or {})
            tool_calls.append(
                ToolCall(
                    tool_name=function.name,
                    args=args,
                    tool_call_id=item.id,
                )
            )
        assistant = AssistantMessage(
            content=getattr(message, "content", "") or "",
            tool_calls=tool_calls,
        )
        usage = getattr(response, "usage", None)
        normalized_usage = ModelUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )
        return ModelResponse(message=assistant, usage=normalized_usage, raw=response)


def normalize_litellm_model(model: str) -> str:
    raw = str(model or "").strip()
    if not raw:
        return raw
    if ":" not in raw:
        return raw
    provider, model_name = split_model_identifier(raw)
    if not provider or not model_name:
        return raw
    return f"{provider}/{model_name}"


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def _to_litellm_messages(messages: list[Message]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        payloads.extend(_expand_litellm_message(message))
    return payloads


def _expand_litellm_message(message: Message) -> list[dict[str, Any]]:
    if message.role == "system":
        return [{"role": "system", "content": message.content}]
    if message.role == "user":
        return [{"role": "user", "content": message.content}]
    if message.role == "assistant":
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": None if message.tool_calls and not message.content else message.content,
        }
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.tool_name,
                        "arguments": _dump_json(tool_call.args),
                    },
                }
                for tool_call in message.tool_calls
            ]
        return [payload]
    if isinstance(message, ToolMessage):
        return [
            {
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "content": _dump_json(result.content),
            }
            for result in message.results
        ]
    raise TypeError(f"Unsupported message type: {type(message)!r}")


def _dump_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=True)

