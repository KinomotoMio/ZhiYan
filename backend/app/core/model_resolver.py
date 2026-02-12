"""Model Resolver — 将 provider 前缀映射为 PydanticAI Model 实例

deepseek:* → DeepSeekProvider
openrouter:* → OpenRouterProvider
其他标准 provider → 返回原字符串由 PydanticAI 处理
"""

import logging

from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


def resolve_model(model_str: str) -> str | OpenAIModel:
    """将 deepseek:/openrouter: 前缀映射为带 API Key 的 Model 实例，
    其他标准 provider 直接返回字符串由 PydanticAI 处理"""
    from app.core.config import settings

    if model_str.startswith("deepseek:") and settings.deepseek_api_key:
        model_name = model_str.split(":", 1)[1]
        return OpenAIModel(
            model_name,
            provider=DeepSeekProvider(api_key=settings.deepseek_api_key),
        )

    if model_str.startswith("openrouter:") and settings.openrouter_api_key:
        model_name = model_str.split(":", 1)[1]
        return OpenAIModel(
            model_name,
            provider=OpenRouterProvider(api_key=settings.openrouter_api_key),
        )

    # openai: 且有自定义 base_url
    if model_str.startswith("openai:") and settings.openai_api_key:
        default_base = "https://api.openai.com/v1"
        if settings.openai_base_url and settings.openai_base_url != default_base:
            model_name = model_str.split(":", 1)[1]
            return OpenAIModel(
                model_name,
                provider=OpenAIProvider(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                ),
            )

    return model_str
