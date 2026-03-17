import asyncio

from pydantic_ai.exceptions import ModelHTTPError

from app.core.config import settings
from app.services.pipeline.graph import PipelineState, stage_select_layouts


def test_layout_selector_retries_with_strong_model_on_channel_error(monkeypatch):
    calls: list[object] = []

    class _Usage:
        requests = 1
        input_tokens = 10
        output_tokens = 10
        total_tokens = 20

        def __str__(self) -> str:  # pragma: no cover
            return "usage"

    class _Output:
        def model_dump(self, *args, **kwargs):  # noqa: ARG002
            return {
                "slides": [
                    {
                        "slide_number": 1,
                        "group": "cover",
                        "sub_group": "default",
                        "variant_id": "title-centered",
                        "reason": "test",
                    },
                    {
                        "slide_number": 2,
                        "group": "closing",
                        "sub_group": "default",
                        "variant_id": "closing-center",
                        "reason": "test",
                    },
                ]
            }

    class _Result:
        output = _Output()

        def usage(self):
            return _Usage()

    async def fake_run(prompt: str, **kwargs):  # noqa: ARG001
        calls.append(kwargs.get("model"))
        if kwargs.get("model") is None:
            raise ModelHTTPError(
                400,
                "openai:minimax/minimax-m2.5",
                {"message": "no available channels for model openai:minimax/minimax-m2.5", "type": "invalid_request_error"},
            )
        return _Result()

    # Ensure fallback model is different so retry path can trigger.
    monkeypatch.setattr(settings, "default_model", "openai:minimax/minimax-m2.5", raising=False)
    monkeypatch.setattr(settings, "fast_model", "", raising=False)
    monkeypatch.setattr(settings, "strong_model", "openai:gpt-4o", raising=False)

    from app.services.agents import layout_selector as layout_selector_mod

    monkeypatch.setattr(layout_selector_mod.layout_selector_agent, "run", fake_run)

    # Keep the rest of stage_select_layouts deterministic and unrelated to taxonomy changes.
    from app.models import layout_registry as layout_registry_mod

    class _Entry:
        variant_id = "title-centered"

    def fake_get_layout(layout_id: str):  # noqa: ARG001
        return _Entry()

    monkeypatch.setattr(layout_registry_mod, "get_all_layouts", lambda: [])
    monkeypatch.setattr(layout_registry_mod, "get_layout", fake_get_layout)
    monkeypatch.setattr(layout_registry_mod, "get_layout_taxonomy_catalog", lambda: "stub")

    from app.services.pipeline import graph as graph_mod

    monkeypatch.setattr(graph_mod, "_serialize_design_traits_from_entry", lambda entry: {})  # noqa: ARG005

    state = PipelineState(
        raw_content="x",
        topic="t",
        num_pages=2,
        job_id="job-test",
        outline={
            "items": [
                {"slide_number": 1, "title": "S1", "suggested_slide_role": "cover"},
                {"slide_number": 2, "title": "S2", "suggested_slide_role": "closing"},
            ]
        },
    )

    asyncio.run(stage_select_layouts(state))

    assert calls and calls[0] is None
    assert calls[1] == settings.strong_model
    meta = state.document_metadata.get("layout_selection") or {}
    assert meta.get("fallback_used") is True
    assert meta.get("model_used") == settings.strong_model
