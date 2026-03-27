from app.models.generation import GenerationJob, GenerationRequestData
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def test_presentation_submission_hydrates_missing_ids_and_content_alias(tmp_path):
    runner = GenerationRunner(GenerationJobStore(tmp_path / "jobs"), GenerationEventBus())
    job = GenerationJob(
        job_id="job-presentation-submit",
        request=GenerationRequestData(topic="直接提交", title="直接提交", resolved_content="测试内容"),
    )
    payload_holder = {
        "presentation": {
            "slides": [
                {
                    "layoutType": "bullet-with-icons",
                    "content": {
                        "title": "关键变化",
                        "items": [
                            {"title": "一", "description": "说明一"},
                            {"title": "二", "description": "说明二"},
                            {"title": "三", "description": "说明三"},
                        ],
                    },
                }
            ]
        }
    }

    payload, presentation = runner._extract_presentation_submission(job, payload_holder)  # noqa: SLF001

    assert payload["presentationId"].startswith("pres-")
    assert payload["title"] == "直接提交"
    assert payload["slides"][0]["slideId"] == "slide-1"
    assert payload["slides"][0]["layoutId"] == "bullet-with-icons"
    assert payload["slides"][0]["contentData"]["title"] == "关键变化"
    assert "content" not in payload["slides"][0]
    assert presentation.slides[0].slide_id == "slide-1"


def test_presentation_submission_returns_hydrated_payload_before_normalization(tmp_path):
    runner = GenerationRunner(GenerationJobStore(tmp_path / "jobs"), GenerationEventBus())
    job = GenerationJob(
        job_id="job-presentation-raw-payload",
        request=GenerationRequestData(topic="直接提交", title="直接提交", resolved_content="测试内容"),
    )
    payload_holder = {
        "presentation": {
            "slides": [
                {
                    "layoutType": "bullet-with-icons",
                    "contentData": {
                        "title": "关键变化",
                        "items": [
                            {"title": "一", "description": ""},
                            {"title": "二", "description": ""},
                            {"title": "三", "description": ""},
                        ],
                    },
                }
            ]
        }
    }

    payload, presentation = runner._extract_presentation_submission(job, payload_holder)  # noqa: SLF001

    assert payload["slides"][0]["contentData"]["items"][0]["description"] == ""
    assert presentation.slides[0].content_data["items"][0]["description"] == "一"


def test_html_prompt_enforces_direct_canvas_first_reveal_output(tmp_path):
    runner = GenerationRunner(GenerationJobStore(tmp_path / "jobs"), GenerationEventBus())
    job = GenerationJob(
        job_id="job-html-prompt",
        output_mode="html",
        request=GenerationRequestData(
            topic="HTML 直出",
            title="HTML 直出",
            resolved_content="测试内容",
            num_pages=6,
        ),
    )
    state = runner._build_state(job)  # noqa: SLF001

    prompt = runner._build_agent_presentation_prompt(job, state)  # noqa: SLF001

    assert "不要先设计结构化 slide schema" in prompt
    assert "1280x720" in prompt
    assert "核心文字放在初始 `opacity: 0`" in prompt
    assert "不要假设有模版系统" in prompt
    assert "不要写成长文档" in prompt
