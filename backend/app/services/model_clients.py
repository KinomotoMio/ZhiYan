from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.model_status import parse_provider
from app.services.generation.agentic.models import LiteLLMModelClient


@dataclass(frozen=True, slots=True)
class LiteLLMRequestConfig:
    model: str
    api_key: str | None = None
    api_base: str | None = None

    def to_request_kwargs(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.api_key is not None:
            payload["api_key"] = self.api_key
        if self.api_base is not None:
            payload["api_base"] = self.api_base
        return payload


def resolve_litellm_request_config(model_name: str) -> LiteLLMRequestConfig:
    normalized_model = str(model_name or "").strip()
    provider = parse_provider(normalized_model)
    api_key: str | None = None
    api_base: str | None = None
    if provider == "openai":
        api_key = str(settings.openai_api_key or "").strip() or None
        api_base = str(settings.openai_base_url or "").strip() or None
    elif provider == "anthropic":
        api_key = str(settings.anthropic_api_key or "").strip() or None
    elif provider == "google-gla":
        api_key = str(settings.google_api_key or "").strip() or None
    elif provider == "deepseek":
        api_key = str(settings.deepseek_api_key or "").strip() or None
    elif provider == "openrouter":
        api_key = str(settings.openrouter_api_key or "").strip() or None
    return LiteLLMRequestConfig(
        model=normalized_model,
        api_key=api_key,
        api_base=api_base,
    )


def create_model_client(
    model_name: str,
    *,
    temperature: float | None = None,
    **extra_kwargs: Any,
) -> LiteLLMModelClient:
    config = resolve_litellm_request_config(model_name)
    return LiteLLMModelClient(
        model=config.model,
        temperature=temperature,
        api_key=config.api_key,
        api_base=config.api_base,
        extra_kwargs=extra_kwargs,
    )
