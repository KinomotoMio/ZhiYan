from app.models.generation import GenerationJob, GenerationRequestData
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def test_presentation_audit_flags_empty_descriptions_and_noisy_repairs(tmp_path):
    runner = GenerationRunner(GenerationJobStore(tmp_path / "jobs"), GenerationEventBus())
    job = GenerationJob(
        job_id="job-audit",
        request=GenerationRequestData(topic="审计测试", title="审计测试", num_pages=3, resolved_content="测试内容"),
    )
    payload_holder = {
        "presentation": {
            "title": "审计测试",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "intro-slide",
                    "layoutId": "intro-slide",
                    "contentData": {"title": "封面", "subtitle": "说明"},
                },
                {
                    "slideId": "slide-2",
                    "layoutType": "outline-slide",
                    "layoutId": "outline-slide",
                    "contentData": {
                        "title": "目录",
                        "sections": [
                            {"title": "一", "description": ""},
                            {"title": "二", "description": ""},
                            {"title": "三", "description": ""},
                            {"title": "四", "description": ""},
                        ],
                    },
                },
                {
                    "slideId": "slide-3",
                    "layoutType": "bullet-with-icons",
                    "layoutId": "bullet-with-icons",
                    "contentData": {
                        "title": "内容",
                        "items": [
                            {"title": "A", "description": ""},
                            {"title": "B", "description": ""},
                            {"title": "C", "description": ""},
                        ],
                    },
                },
            ],
        }
    }

    payload, presentation = runner._extract_presentation_submission(job, payload_holder)  # noqa: SLF001
    audit = runner._audit_generated_presentation(job, payload, presentation)  # noqa: SLF001

    assert audit["issues"] == []
    assert any("sections.description" in issue for issue in audit["warnings"])
