from __future__ import annotations

import base64
import json
import re
from typing import Any, TypeVar

from litellm import acompletion
from pydantic import BaseModel

from app.services.generation.agentic.models import ModelUsage, normalize_litellm_model
from app.services.generation.agentic.types import SystemMessage, UserMessage
from app.services.model_clients import create_model_client, resolve_litellm_request_config


ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", re.IGNORECASE)


def _extract_json_candidate(text: str) -> str | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    fenced = _JSON_BLOCK_RE.search(cleaned)
    if fenced:
        return fenced.group(1).strip()
    if cleaned.startswith("{") or cleaned.startswith("["):
        return cleaned
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")
    indices = [index for index in (first_brace, first_bracket) if index >= 0]
    if not indices:
        return None
    return cleaned[min(indices) :].strip()


def _normalize_usage(raw_usage: Any) -> ModelUsage:
    return ModelUsage(
        prompt_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(raw_usage, "total_tokens", 0) or 0,
    )


async def complete_text(
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = 0.0,
) -> tuple[str, ModelUsage]:
    client = create_model_client(model_name, temperature=temperature)
    response = await client.complete(
        [
            SystemMessage(content=system_prompt),
            UserMessage(content=user_prompt),
        ],
        [],
    )
    return str(response.message.content or "").strip(), response.usage


async def complete_multimodal_text(
    *,
    model_name: str,
    system_prompt: str,
    user_content: list[dict[str, Any]],
    temperature: float | None = 0.0,
) -> tuple[str, ModelUsage]:
    config = resolve_litellm_request_config(model_name)
    request: dict[str, Any] = {
        "model": normalize_litellm_model(config.model),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if temperature is not None:
        request["temperature"] = temperature
    request.update(config.to_request_kwargs())
    response = await acompletion(**request)
    choice = response.choices[0]
    message = choice.message
    return str(getattr(message, "content", "") or "").strip(), _normalize_usage(getattr(response, "usage", None))


async def generate_structured_output(
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    output_model: type[ModelT],
    temperature: float | None = 0.0,
    max_attempts: int = 2,
) -> tuple[ModelT, str, ModelUsage]:
    latest_text = ""
    latest_usage = ModelUsage()
    repair_note = ""
    schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
    for _attempt in range(max_attempts):
        prompt = (
            f"{user_prompt.strip()}\n\n"
            "只返回一个 JSON 对象，不要包含解释、Markdown 或代码块。\n"
            f"必须满足这个 JSON Schema：\n{schema}"
        )
        if repair_note:
            prompt = f"{prompt}\n\n上一次输出无法解析，请修正：{repair_note}"
        latest_text, latest_usage = await complete_text(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
        )
        candidate = _extract_json_candidate(latest_text)
        if not candidate:
            repair_note = "没有返回合法 JSON。"
            continue
        try:
            return output_model.model_validate_json(candidate), latest_text, latest_usage
        except Exception as exc:
            repair_note = str(exc)
    raise ValueError(f"Failed to generate structured output for {output_model.__name__}: {repair_note or latest_text}")


def build_image_part(png_bytes: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{encoded}",
        },
    }
