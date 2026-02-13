"""应用配置 — LLM keys, paths, 限制参数"""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # LLM 配置
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    openrouter_api_key: str = ""

    # PydanticAI 模型标识
    default_model: str = "openai:gpt-4o-mini"
    strong_model: str = "openai:gpt-4o"
    vision_model: str = "openai:gpt-4o-mini"
    fast_model: str = ""  # 用于清洗/分块分析等简单任务，空值时回退到 default_model

    # 路径
    project_root: Path = Path(__file__).resolve().parents[3]
    skills_dir: Path = Path(__file__).resolve().parents[3] / "skills"

    # 文件大小 / 页数限制
    max_upload_size_mb: int = 50
    max_slide_pages: int = 50
    max_document_tokens: int = 100_000

    # 生成超时（秒）
    generate_timeout_seconds: int = 300
    sse_heartbeat_seconds: float = 10.0

    # 日志
    log_level: str = "INFO"
    log_format: str = "text"  # text | json
    log_sse_debug: bool = False

    # TTS
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def reload_settings(overrides: dict | None = None) -> None:
    """从 JSON 持久化文件加载用户设置，合并到全局 settings"""
    from app.core.settings_store import load_user_settings

    stored = load_user_settings()
    if overrides:
        stored.update(overrides)

    next_settings = Settings(**stored) if stored else Settings()
    for field_name in type(next_settings).model_fields:
        setattr(settings, field_name, getattr(next_settings, field_name))

    if stored:
        logger.info(
            "Settings reloaded with %d overrides (object_id=%s)",
            len(stored),
            id(settings),
        )
    else:
        logger.info("Settings reloaded from defaults (object_id=%s)", id(settings))
