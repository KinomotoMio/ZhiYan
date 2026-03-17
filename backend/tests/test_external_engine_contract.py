import asyncio

from app.models.slide import Presentation, Slide
from app.services.generation.external_adapter_contract import (
    ExternalEngineAdapter,
    ExternalEngineError,
    ExternalEngineRequest,
    ExternalEngineResult,
)


def test_external_engine_error_payload() -> None:
    err = ExternalEngineError(code="ENGINE_TIMEOUT", message="timed out", retriable=True)
    payload = err.to_payload()
    assert payload["error_code"] == "ENGINE_TIMEOUT"
    assert payload["error_message"] == "timed out"
    assert payload["retriable"] is True


def test_external_engine_contract_is_runtime_checkable() -> None:
    class DemoAdapter:
        engine_id = "demo"

        async def generate(self, request: ExternalEngineRequest, *, timeout_seconds: float) -> ExternalEngineResult:
            pres = Presentation(
                presentationId="pres-demo",
                title=request.topic or "Demo",
                slides=[
                    Slide(
                        slideId="slide-1",
                        layoutType="blank",
                        layoutId="blank",
                        contentData={"title": "ok"},
                        components=[],
                    )
                ],
            )
            return ExternalEngineResult(presentation=pres, artifacts={"timeout_seconds": timeout_seconds})

    adapter = DemoAdapter()
    assert isinstance(adapter, ExternalEngineAdapter)

    async def _case():
        req = ExternalEngineRequest(job_id="job-1", topic="T", resolved_content="C", num_pages=3)
        result = await adapter.generate(req, timeout_seconds=1.0)
        assert result.presentation.title == "T"
        assert result.artifacts["timeout_seconds"] == 1.0

    asyncio.run(_case())
