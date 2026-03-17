"""应用配置 — LLM keys, paths, 限制参数"""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (
            (candidate / "backend" / "pyproject.toml").exists()
            and (candidate / "frontend" / "package.json").exists()
            and (candidate / "shared").exists()
        ):
            return candidate

    raise RuntimeError("Could not determine project root from backend config location.")


PROJECT_ROOT = _find_project_root()


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
    project_root: Path = PROJECT_ROOT
    skills_dir: Path = PROJECT_ROOT / "skills"
    db_path: Path = PROJECT_ROOT / "data" / "zhiyan.db"
    uploads_dir: Path = PROJECT_ROOT / "data" / "uploads"

    # 文件大小 / 页数限制
    max_upload_size_mb: int = 50
    max_slide_pages: int = 50
    max_document_tokens: int = 100_000

    # 生成超时（秒）
    generate_timeout_seconds: int = 300
    job_timeout_seconds: int = 1800
    outline_timeout_seconds: int = 90
    layout_timeout_seconds: int = 45
    per_slide_timeout_seconds: int = 75
    verify_timeout_seconds: int = 90
    max_fix_passes: int = 1
    enable_vision_verification: bool = True
    sse_heartbeat_seconds: float = 10.0

    # 日志
    log_level: str = "INFO"
    log_format: str = "text"  # text | json
    log_sse_debug: bool = False

    # Generation engines (C-plan foundation). Default keeps current internal pipeline.
    generation_primary_engine: str = "internal_v2"  # internal_v2 | slidev | presenton

    # TTS
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
    ]
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

    model_config = {
        "env_file": PROJECT_ROOT / ".env",
        "env_file_encoding": "utf-8",
    }


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
