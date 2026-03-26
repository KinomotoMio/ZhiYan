from app.models.generation import StageStatus
from app.services.generation.loop_planner import GenerationLoopPlanner, LoopHistoryItem
from app.services.generation.tool_registry import GenerationTool, GenerationToolRegistry
from app.services.pipeline.graph import PipelineState


def _registry() -> GenerationToolRegistry:
    async def _noop(state, progress, on_slide):  # noqa: ARG001
        return None

    return GenerationToolRegistry(
        [
            GenerationTool("parse_document", StageStatus.PARSE, "parse", lambda: 1.0, _noop),
            GenerationTool("generate_outline", StageStatus.OUTLINE, "outline", lambda: 1.0, _noop),
            GenerationTool("select_layouts", StageStatus.LAYOUT, "layout", lambda: 1.0, _noop),
            GenerationTool("generate_slides", StageStatus.SLIDES, "slides", lambda: 1.0, _noop),
            GenerationTool("resolve_assets", StageStatus.ASSETS, "assets", lambda: 1.0, _noop),
            GenerationTool("verify_slides", StageStatus.VERIFY, "verify", lambda: 1.0, _noop),
        ]
    )


def test_deterministic_planner_walks_missing_state_in_order():
    planner = GenerationLoopPlanner()
    state = PipelineState(raw_content="x", topic="t", num_pages=3)
    registry = _registry()

    decision = planner._deterministic_decide(state=state, registry=registry, history=[])  # noqa: SLF001
    assert decision.tool_name == "parse_document"

    state.document_metadata = {"char_count": 1}
    decision = planner._deterministic_decide(state=state, registry=registry, history=[])  # noqa: SLF001
    assert decision.tool_name == "generate_outline"

    state.outline = {"items": [{"slide_number": 1, "title": "封面"}]}
    decision = planner._deterministic_decide(state=state, registry=registry, history=[])  # noqa: SLF001
    assert decision.tool_name == "select_layouts"


def test_deterministic_planner_completes_after_verify():
    planner = GenerationLoopPlanner()
    registry = _registry()
    state = PipelineState(raw_content="x", topic="t", num_pages=3)
    state.document_metadata = {"char_count": 1}
    state.outline = {"items": [{"slide_number": 1, "title": "封面"}]}
    state.layout_selections = [{"slide_number": 1, "layout_id": "intro-slide"}]
    state.slide_contents = [{"slide_number": 1, "layout_id": "intro-slide", "content_data": {"title": "封面"}}]
    state.slides = []

    history = [
        LoopHistoryItem("parse_document", StageStatus.PARSE),
        LoopHistoryItem("generate_outline", StageStatus.OUTLINE),
        LoopHistoryItem("select_layouts", StageStatus.LAYOUT),
        LoopHistoryItem("generate_slides", StageStatus.SLIDES),
    ]
    decision = planner._deterministic_decide(state=state, registry=registry, history=history)  # noqa: SLF001
    assert decision.tool_name == "resolve_assets"

    state.slides = [object()]
    history.append(LoopHistoryItem("resolve_assets", StageStatus.ASSETS))
    decision = planner._deterministic_decide(state=state, registry=registry, history=history)  # noqa: SLF001
    assert decision.tool_name == "verify_slides"

    history.append(LoopHistoryItem("verify_slides", StageStatus.VERIFY))
    decision = planner._deterministic_decide(state=state, registry=registry, history=history)  # noqa: SLF001
    assert decision.action == "complete"
