"""应用配置 — LLM keys, paths, 限制参数"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM 配置
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # PydanticAI 模型标识
    default_model: str = "openai:gpt-4o-mini"
    strong_model: str = "openai:gpt-4o"

    # 路径
    project_root: Path = Path(__file__).resolve().parents[3]
    skills_dir: Path = Path(__file__).resolve().parents[3] / "skills"

    # 文件大小 / 页数限制
    max_upload_size_mb: int = 50
    max_slide_pages: int = 50
    max_document_tokens: int = 100_000

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
