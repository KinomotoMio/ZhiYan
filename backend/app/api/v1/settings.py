"""GET/PUT /api/v1/settings - 用户设置管理"""

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.model_status import ModelStatus, build_model_status
from app.utils.security import HTTPS_DOMAIN_POLICY_ERROR, get_safe_httpx_client

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

_ALLOWED_FIELDS = {
    "openai_api_key",
    "openai_base_url",
    "anthropic_api_key",
    "google_api_key",
    "deepseek_api_key",
    "openrouter_api_key",
    "default_model",
    "strong_model",
    "vision_model",
    "fast_model",
    "tts_model",
    "tts_voice",
    "enable_vision_verification",
}

_VALIDATION_URL_POLICY = "https_domain_only"
_NETWORK_ERROR_PREFIX = "网络或运行环境异常，无法完成校验"


def _mask_key(key: str) -> str:
    """脱敏 API key: sk-abc...xyz4"""
    if not key or len(key) < 8:
        return key
    return f"{key[:5]}...{key[-4:]}"


class SettingsResponse(BaseModel):
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    openrouter_api_key: str = ""
    default_model: str = ""
    strong_model: str = ""
    vision_model: str = ""
    fast_model: str = ""
    tts_model: str = ""
    tts_voice: str = ""
    enable_vision_verification: bool = True
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    has_google_key: bool = False
    has_deepseek_key: bool = False
    has_openrouter_key: bool = False
    default_model_status: ModelStatus = Field(default_factory=ModelStatus)
    strong_model_status: ModelStatus = Field(default_factory=ModelStatus)
    vision_model_status: ModelStatus = Field(default_factory=ModelStatus)
    fast_model_status: ModelStatus = Field(default_factory=ModelStatus)


class SettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None
    openrouter_api_key: str | None = None
    default_model: str | None = None
    strong_model: str | None = None
    vision_model: str | None = None
    fast_model: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    enable_vision_verification: bool | None = None


class ValidateRequest(BaseModel):
    provider: str  # "openai" | "anthropic" | "google" | "deepseek" | "openrouter"
    api_key: str
    base_url: str | None = None


class ValidateResponse(BaseModel):
    valid: bool
    message: str


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """返回当前配置，API keys 脱敏显示。"""
    from app.core.config import settings

    default_model_status = build_model_status(settings.default_model, settings)
    strong_model_status = build_model_status(settings.strong_model, settings)
    vision_model_status = build_model_status(settings.vision_model, settings)
    fast_model_status = build_model_status(
        settings.fast_model or settings.default_model, settings
    )

    return SettingsResponse(
        openai_api_key=_mask_key(settings.openai_api_key),
        openai_base_url=settings.openai_base_url,
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        google_api_key=_mask_key(settings.google_api_key),
        deepseek_api_key=_mask_key(settings.deepseek_api_key),
        openrouter_api_key=_mask_key(settings.openrouter_api_key),
        default_model=settings.default_model,
        strong_model=settings.strong_model,
        vision_model=settings.vision_model,
        fast_model=settings.fast_model,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        enable_vision_verification=settings.enable_vision_verification,
        has_openai_key=bool(settings.openai_api_key),
        has_anthropic_key=bool(settings.anthropic_api_key),
        has_google_key=bool(settings.google_api_key),
        has_deepseek_key=bool(settings.deepseek_api_key),
        has_openrouter_key=bool(settings.openrouter_api_key),
        default_model_status=default_model_status,
        strong_model_status=strong_model_status,
        vision_model_status=vision_model_status,
        fast_model_status=fast_model_status,
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdate):
    """更新配置并使 agent 缓存失效。"""
    from app.core.config import reload_settings
    from app.core.settings_store import (
        invalidate_agents,
        load_user_settings,
        save_user_settings,
    )

    current = load_user_settings()
    updates = req.model_dump(exclude_none=True)

    for key in list(updates.keys()):
        if key not in _ALLOWED_FIELDS:
            del updates[key]
        elif isinstance(updates[key], str) and "..." in updates[key]:
            del updates[key]

    current.update(updates)
    save_user_settings(current)
    reload_settings()
    invalidate_agents()

    return await get_settings()


def _normalize_base_url(base_url: str | None, default: str) -> str:
    candidate = (base_url or default).strip()
    return candidate.rstrip("/")


def _validation_message_for_status(status_code: int, success_message: str) -> ValidateResponse:
    if status_code in (200, 529):
        return ValidateResponse(valid=True, message=success_message)
    if status_code == 401:
        return ValidateResponse(valid=False, message="API Key 无效")
    return ValidateResponse(valid=False, message=f"验证失败: HTTP {status_code}")


def _network_error_message(error: Exception) -> str:
    detail = str(error).strip()
    if not detail:
        return _NETWORK_ERROR_PREFIX
    return f"{_NETWORK_ERROR_PREFIX}: {detail}"


@router.post("/validate", response_model=ValidateResponse)
async def validate_api_key(req: ValidateRequest):
    """验证 API key，对不同 provider 发送最小请求。"""
    try:
        if req.provider == "openai":
            base = _normalize_base_url(req.base_url, "https://api.openai.com/v1")
            async with get_safe_httpx_client(
                timeout=15,
                url_policy=_VALIDATION_URL_POLICY,
            ) as client:
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
            return _validation_message_for_status(resp.status_code, "OpenAI API Key 验证成功")

        if req.provider == "anthropic":
            async with get_safe_httpx_client(
                timeout=15,
                url_policy=_VALIDATION_URL_POLICY,
            ) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": req.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
            return _validation_message_for_status(resp.status_code, "Anthropic API Key 验证成功")

        if req.provider == "google":
            async with get_safe_httpx_client(
                timeout=15,
                url_policy=_VALIDATION_URL_POLICY,
            ) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={req.api_key}"
                )
            return _validation_message_for_status(resp.status_code, "Google API Key 验证成功")

        if req.provider == "deepseek":
            async with get_safe_httpx_client(
                timeout=15,
                url_policy=_VALIDATION_URL_POLICY,
            ) as client:
                resp = await client.get(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
            return _validation_message_for_status(resp.status_code, "DeepSeek API Key 验证成功")

        if req.provider == "openrouter":
            async with get_safe_httpx_client(
                timeout=15,
                url_policy=_VALIDATION_URL_POLICY,
            ) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
            return _validation_message_for_status(resp.status_code, "OpenRouter API Key 验证成功")

        return ValidateResponse(valid=False, message=f"不支持的 provider: {req.provider}")
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == 400 and HTTPS_DOMAIN_POLICY_ERROR in detail:
            return ValidateResponse(valid=False, message=detail)
        logger.warning("API key validation blocked: %s", detail)
        return ValidateResponse(valid=False, message=f"验证出错: {detail}")
    except httpx.HTTPError as exc:
        logger.warning("API key validation network error: %s", exc)
        return ValidateResponse(valid=False, message=_network_error_message(exc))
    except Exception as exc:
        logger.warning("API key validation error: %s", exc)
        return ValidateResponse(valid=False, message=_network_error_message(exc))
