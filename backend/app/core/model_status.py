"""模型配置状态判定"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ModelStatus(BaseModel):
    model: str = ""
    provider: str = ""
    ready: bool = False
    message: str = ""


_PROVIDER_KEY_FIELD: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google-gla": "google_api_key",
    "deepseek": "deepseek_api_key",
    "openrouter": "openrouter_api_key",
}


def parse_provider(model_str: str) -> str:
    model = model_str.strip()
    if not model or ":" not in model:
        return ""
    provider, _, _ = model.partition(":")
    return provider.strip()


def provider_required_key(provider: str) -> str | None:
    return _PROVIDER_KEY_FIELD.get(provider)


def build_model_status(model_str: str, settings: Any) -> ModelStatus:
    model = model_str.strip()
    if not model:
        return ModelStatus(
            model="",
            provider="",
            ready=False,
            message="请先在设置中选择模型",
        )

    provider = parse_provider(model)
    if not provider:
        return ModelStatus(
            model=model,
            provider="",
            ready=True,
            message="未检测到 provider 前缀，将按原始模型名尝试调用",
        )

    _, _, model_name = model.partition(":")
    if not model_name.strip():
        return ModelStatus(
            model=model,
            provider=provider,
            ready=False,
            message="模型格式无效，请使用 provider:model-name",
        )

    key_field = provider_required_key(provider)
    if key_field is None:
        return ModelStatus(
            model=model,
            provider=provider,
            ready=True,
            message=f"Provider {provider} 未内置 API Key 校验，将在运行时尝试调用",
        )

    if getattr(settings, key_field, ""):
        return ModelStatus(
            model=model,
            provider=provider,
            ready=True,
            message=f"{provider} API Key 已配置，可直接生成",
        )

    return ModelStatus(
        model=model,
        provider=provider,
        ready=False,
        message=f"模型 {model} 需要 {provider} API Key，请先在设置中配置",
    )
