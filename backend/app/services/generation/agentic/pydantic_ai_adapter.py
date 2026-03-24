"""Thin optional adapter from the internal agentic protocol to PydanticAI."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import logging
from typing import Any

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, infer_model
from pydantic_ai.tools import ToolDefinition

from app.core.config import settings
from app.core.model_resolver import resolve_model
from app.services.generation.agentic.types import (
    AgenticMessage,
    AgenticModelClient,
    AssistantMessage,
    ToolCall,
    UserMessage,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_MAX_REQUEST_RETRIES = 3
_BASE_RETRY_DELAY_SECONDS = 5.0


def build_pydantic_ai_model(model_name: Model | str | None = None) -> Model:
    resolved = resolve_model(model_name or settings.strong_model)
    if isinstance(resolved, Model):
        return resolved
    return infer_model(resolved)


class PydanticAIModelClient(AgenticModelClient):
    """Adapter that keeps PydanticAI at the boundary only."""

    def __init__(self, model: Model | str | None = None) -> None:
        self._model = build_pydantic_ai_model(model)

    async def complete(
        self,
        messages: Sequence[AgenticMessage],
        tools: Sequence[dict[str, Any]],
    ) -> AssistantMessage:
        response = await self._request_with_retries(messages, tools)
        return self._from_model_response(response)

    async def _request_with_retries(
        self,
        messages: Sequence[AgenticMessage],
        tools: Sequence[dict[str, Any]],
    ) -> ModelResponse:
        converted_messages = self._to_model_messages(messages)
        request_parameters = ModelRequestParameters(
            function_tools=[self._to_tool_definition(tool) for tool in tools],
            allow_text_output=True,
        )

        attempt = 0
        while True:
            try:
                return await self._model.request(
                    converted_messages,
                    None,
                    request_parameters,
                )
            except ModelHTTPError as exc:
                attempt += 1
                if attempt >= _MAX_REQUEST_RETRIES or exc.status_code not in _RETRYABLE_STATUS_CODES:
                    logger.exception("agentic model request failed")
                    raise

                delay_seconds = _BASE_RETRY_DELAY_SECONDS * attempt
                logger.warning(
                    "agentic model request retrying after transient provider error",
                    extra={
                        "status_code": exc.status_code,
                        "model_name": exc.model_name,
                        "attempt": attempt,
                        "delay_seconds": delay_seconds,
                    },
                )
                await asyncio.sleep(delay_seconds)
            except Exception:
                logger.exception("agentic model request failed")
                raise

    def _to_model_messages(self, messages: Sequence[AgenticMessage]) -> list[ModelMessage]:
        converted: list[ModelMessage] = []
        for message in messages:
            if isinstance(message, UserMessage):
                parts = []
                for part in message.parts:
                    if isinstance(part, str):
                        parts.append(UserPromptPart(part))
                    elif part.is_error:
                        parts.append(
                            RetryPromptPart(
                                content=str(part.content),
                                tool_name=part.tool_name,
                                tool_call_id=part.tool_call_id,
                            )
                        )
                    else:
                        parts.append(
                            ToolReturnPart(
                                tool_name=part.tool_name,
                                content=part.content,
                                tool_call_id=part.tool_call_id,
                                metadata=part.metadata,
                            )
                        )
                converted.append(ModelRequest(parts=parts, instructions=message.instructions))
            else:
                parts = []
                for part in message.parts:
                    if isinstance(part, str):
                        parts.append(TextPart(part))
                    else:
                        parts.append(
                            ToolCallPart(
                                tool_name=part.tool_name,
                                args=part.args,
                                tool_call_id=part.tool_call_id,
                            )
                        )
                converted.append(
                    ModelResponse(
                        parts=parts,
                        provider_name=message.provider_name,
                        model_name=message.model_name,
                    )
                )
        return converted

    @staticmethod
    def _from_model_response(response: ModelResponse) -> AssistantMessage:
        parts: list[str | ToolCall] = []
        for part in response.parts:
            if isinstance(part, TextPart):
                parts.append(part.content)
            elif isinstance(part, ToolCallPart):
                parts.append(
                    ToolCall(
                        tool_name=part.tool_name,
                        args=part.args_as_dict(),
                        tool_call_id=part.tool_call_id,
                    )
                )
        return AssistantMessage(
            parts=parts,
            provider_name=response.provider_name,
            model_name=response.model_name,
        )

    @staticmethod
    def _to_tool_definition(tool: dict[str, Any]) -> ToolDefinition:
        return ToolDefinition(
            name=str(tool["name"]),
            description=str(tool.get("description") or ""),
            parameters_json_schema=tool.get("input_schema") or {"type": "object", "properties": {}},
        )
