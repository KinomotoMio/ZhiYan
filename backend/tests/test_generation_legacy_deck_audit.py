from app.models.generation import GenerationJob, GenerationRequestData
from app.services.generation.legacy.deck_adapter import AgentDeck, deck_to_slides
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def test_legacy_deck_audit_flags_empty_descriptions_and_noisy_repairs(tmp_path):
    runner = GenerationRunner(GenerationJobStore(tmp_path / "jobs"), GenerationEventBus())
    job = GenerationJob(
        job_id="job-audit",
        request=GenerationRequestData(topic="审计测试", num_pages=3, resolved_content="测试内容"),
    )
    deck = AgentDeck.model_validate(
        {
            "title": "审计测试",
            "slides": [
                {
                    "slideNumber": 1,
                    "title": "封面",
                    "role": "cover",
                    "layoutHint": "intro-slide",
                    "subtitle": "说明",
                },
                {
                    "slideNumber": 2,
                    "title": "目录",
                    "role": "agenda",
                    "layoutHint": "outline-slide",
                    "sections": [
                        {"title": "一", "description": ""},
                        {"title": "二", "description": ""},
                        {"title": "三", "description": ""},
                        {"title": "四", "description": ""},
                    ],
                },
                {
                    "slideNumber": 3,
                    "title": "内容",
                    "role": "narrative",
                    "layoutHint": "bullet-with-icons",
                    "items": [
                        {"title": "A", "description": ""},
                        {"title": "B", "description": ""},
                        {"title": "C", "description": ""},
                    ],
                },
            ],
        }
    )

    audit = runner._audit_generated_deck(job, deck, deck_to_slides(deck))  # noqa: SLF001
    assert audit["issues"]
    assert any("items.description 不能为空" in issue for issue in audit["issues"])
    assert any("sections.description 不能为空" in issue for issue in audit["issues"])
