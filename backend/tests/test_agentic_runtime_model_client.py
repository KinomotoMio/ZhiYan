from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.generation.agentic.models import LiteLLMModelClient, normalize_litellm_model
from app.services.generation.agentic.types import AssistantMessage, UserMessage


def test_normalize_litellm_model_converts_internal_provider_prefix():
    assert normalize_litellm_model("openai:gpt-4o") == "openai/gpt-4o"
    assert normalize_litellm_model("openrouter:moonshotai/kimi-k2.5") == "openrouter/moonshotai/kimi-k2.5"
    assert normalize_litellm_model("openai:MiniMax-M2.7-highspeed") == "openai/MiniMax-M2.7-highspeed"
    assert normalize_litellm_model("minimax/MiniMax-M2.7-highspeed") == "minimax/MiniMax-M2.7-highspeed"


@pytest.mark.asyncio
async def test_litellm_client_sends_normalized_model(monkeypatch):
    seen: dict[str, str] = {}

    async def fake_acompletion(**kwargs):
        seen["model"] = kwargs["model"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    monkeypatch.setattr("app.services.generation.agentic.models.acompletion", fake_acompletion)

    client = LiteLLMModelClient(model="openai:MiniMax-M2.7-highspeed")
    response = await client.complete([UserMessage(content="hello")], [])

    assert seen["model"] == "openai/MiniMax-M2.7-highspeed"
    assert isinstance(response.message, AssistantMessage)
    assert response.message.content == "ok"
