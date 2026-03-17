import json

import app.services.skill_runtime.executor as executor
from app.core import config, settings_store
from app.core.config import reload_settings
from app.core.model_status import build_model_status


def test_reload_settings_updates_existing_import_references(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "default_model": "openrouter:moonshotai/kimi-k2.5",
                "strong_model": "openrouter:moonshotai/kimi-k2.5",
                "vision_model": "openrouter:moonshotai/kimi-k2.5",
                "openrouter_api_key": "sk-or-test",
                "enable_vision_verification": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "_SETTINGS_FILE", settings_path)

    before_id = id(config.settings)
    assert id(executor.settings) == before_id

    reload_settings()

    assert id(config.settings) == before_id
    assert id(executor.settings) == before_id
    assert config.settings.default_model == "openrouter:moonshotai/kimi-k2.5"
    assert executor.settings.default_model == "openrouter:moonshotai/kimi-k2.5"
    assert config.settings.enable_vision_verification is False


def test_build_model_status_for_known_and_unknown_providers():
    # Ensure this test is stable even when developers have API keys set in env/.env.
    test_settings = config.Settings(
        openai_api_key="",
        anthropic_api_key="",
        google_api_key="",
        deepseek_api_key="",
        openrouter_api_key="",
    )

    missing_key_status = build_model_status("openai:gpt-4o-mini", test_settings)
    assert missing_key_status.provider == "openai"
    assert missing_key_status.ready is False
    assert "需要 openai API Key" in missing_key_status.message

    test_settings.openai_api_key = "sk-test"
    ready_status = build_model_status("openai:gpt-4o-mini", test_settings)
    assert ready_status.ready is True

    unknown_provider_status = build_model_status("moonshot:kimi-k2.5", test_settings)
    assert unknown_provider_status.provider == "moonshot"
    assert unknown_provider_status.ready is True

    invalid_model_status = build_model_status("openrouter:", test_settings)
    assert invalid_model_status.ready is False
