from __future__ import annotations

import asyncio

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart

from app.services.generation.agentic.pydantic_ai_adapter import PydanticAIModelClient
from app.services.generation.agentic.types import UserMessage


def test_pydantic_ai_adapter_retries_transient_model_http_errors(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    class FakeModel:
        async def request(self, messages, deps, params):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ModelHTTPError(429, "minimax/minimax-m2.5", {"message": "rate limited"})
            return ModelResponse(parts=[TextPart("done")])

    async def fake_sleep(delay_seconds: float):
        sleep_calls.append(delay_seconds)

    monkeypatch.setattr("app.services.generation.agentic.pydantic_ai_adapter.asyncio.sleep", fake_sleep)

    async def _case():
        client = PydanticAIModelClient.__new__(PydanticAIModelClient)
        client._model = FakeModel()
        response = await client.complete([UserMessage(parts=["hello"])], [])
        assert response.parts == ["done"]

    asyncio.run(_case())
    assert attempts["count"] == 3
    assert sleep_calls == [5.0, 10.0]


def test_pydantic_ai_adapter_does_not_retry_non_retryable_http_errors():
    attempts = {"count": 0}

    class FakeModel:
        async def request(self, messages, deps, params):
            attempts["count"] += 1
            raise ModelHTTPError(400, "minimax/minimax-m2.5", {"message": "bad request"})

    async def _case():
        client = PydanticAIModelClient.__new__(PydanticAIModelClient)
        client._model = FakeModel()
        try:
            await client.complete([UserMessage(parts=["hello"])], [])
        except ModelHTTPError as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("expected ModelHTTPError")

    asyncio.run(_case())
    assert attempts["count"] == 1
