"""设置持久化层 — JSON 文件读写 + Agent 缓存失效"""

import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_SETTINGS_FILE: Path | None = None


def _get_settings_path() -> Path:
    global _SETTINGS_FILE
    if _SETTINGS_FILE is None:
        _SETTINGS_FILE = settings.project_root / "data" / "settings.json"
    return _SETTINGS_FILE


def load_user_settings() -> dict:
    """从 data/settings.json 读取用户设置"""
    path = _get_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load settings: %s", e)
        return {}


def save_user_settings(data: dict) -> None:
    """写入 settings.json"""
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Settings saved to %s", path)


def invalidate_agents() -> None:
    """重置所有 agent 的缓存，使其在下次调用时使用新设置重建"""
    from app.services.agents import chunk_analyzer
    from app.services.agents import outline_synthesizer
    from app.services.agents import slide_generator
    from app.services.agents import chat_agent
    from app.services.agents import layout_verifier
    from app.services.agents import document_planner
    from app.services.agents import document_cleaner

    for mod in [
        chunk_analyzer,
        outline_synthesizer,
        slide_generator,
        chat_agent,
        layout_verifier,
        document_planner,
        document_cleaner,
    ]:
        mod._agent = None

    logger.info("All agent caches invalidated")
