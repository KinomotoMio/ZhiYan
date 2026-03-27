import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.generation import GenerationJob, GenerationRequestData, JobStatus, StageStatus
from app.services.generation.job_store import GenerationJobStore


def _base_job(status: JobStatus, *, session_id: str) -> GenerationJob:
    return GenerationJob(
        job_id="job-fix-api",
        status=status,
        current_stage=StageStatus.VERIFY if status == JobStatus.WAITING_FIX_REVIEW else StageStatus.COMPLETE,
        request=GenerationRequestData(topic="测试", resolved_content="测试内容", session_id=session_id),
        outline_accepted=True,
        slides=[
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {"title": "第一页"},
                "components": [],
            }
        ],
    )


def test_fix_api_preview_apply_skip_success(monkeypatch, tmp_path):
    from app.api.v1 import sessions as sessions_api

    class _Runner:
        def __init__(self):
            self.preview_args = None
            self.apply_args = None
            self.skip_args = None

        async def preview_fix(self, job_id: str, slide_ids=None):
            self.preview_args = (job_id, slide_ids)
            return preview_job

        async def apply_fix(self, job_id: str, slide_ids):
            self.apply_args = (job_id, slide_ids)
            return apply_job

        async def skip_fix(self, job_id: str):
            self.skip_args = job_id
            return skip_job

    runner = _Runner()
    monkeypatch.setattr(sessions_api, "generation_runner", runner)

    client = TestClient(app)
    session_resp = client.post("/api/v1/sessions", json={"title": "修复测试"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]
    job_store = GenerationJobStore(tmp_path / "jobs")
    base_job = _base_job(JobStatus.WAITING_FIX_REVIEW, session_id=session_id)
    asyncio.run(job_store.create_job(base_job))
    monkeypatch.setattr(sessions_api, "job_store", job_store)

    preview_job = _base_job(JobStatus.WAITING_FIX_REVIEW, session_id=session_id)
    preview_job.fix_preview_slides = [
        {
            "slideId": "slide-1",
            "layoutType": "bullet-with-icons",
            "layoutId": "bullet-with-icons",
            "contentData": {"title": "第一页（修复）"},
            "components": [],
        }
    ]
    preview_job.fix_preview_source_ids = ["slide-1"]

    apply_job = _base_job(JobStatus.COMPLETED, session_id=session_id)
    apply_job.presentation = {
        "presentationId": "pres-fix",
        "title": "测试",
        "slides": apply_job.slides,
    }

    skip_job = _base_job(JobStatus.COMPLETED, session_id=session_id)
    skip_job.presentation = {
        "presentationId": "pres-skip",
        "title": "测试",
        "slides": skip_job.slides,
    }

    preview_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs/job-fix-api/fix/preview",
        json={"slide_ids": ["slide-1"]},
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["status"] == "waiting_fix_review"
    assert runner.preview_args == ("job-fix-api", ["slide-1"])

    apply_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs/job-fix-api/fix/apply",
        json={"slide_ids": ["slide-1"]},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "completed"
    assert runner.apply_args == ("job-fix-api", ["slide-1"])

    skip_resp = client.post(f"/api/v1/sessions/{session_id}/generation/jobs/job-fix-api/fix/skip")
    assert skip_resp.status_code == 200
    assert skip_resp.json()["status"] == "completed"
    assert runner.skip_args == "job-fix-api"


def test_fix_apply_returns_409_on_runtime_error(monkeypatch, tmp_path):
    from app.api.v1 import sessions as sessions_api

    class _Runner:
        async def apply_fix(self, job_id: str, slide_ids):
            raise RuntimeError("当前状态不支持应用修复")

    monkeypatch.setattr(sessions_api, "generation_runner", _Runner())
    client = TestClient(app)
    session_resp = client.post("/api/v1/sessions", json={"title": "修复测试"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]
    job_store = GenerationJobStore(tmp_path / "jobs")
    asyncio.run(job_store.create_job(_base_job(JobStatus.WAITING_FIX_REVIEW, session_id=session_id)))
    monkeypatch.setattr(sessions_api, "job_store", job_store)

    resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs/job-fix-api/fix/apply",
        json={"slide_ids": ["slide-1"]},
    )
    assert resp.status_code == 409
    assert "当前状态不支持应用修复" in resp.json()["detail"]


def test_fix_skip_returns_404_on_missing_job(monkeypatch, tmp_path):
    from app.api.v1 import sessions as sessions_api

    class _Runner:
        async def skip_fix(self, job_id: str):
            raise ValueError("Job not found")

    monkeypatch.setattr(sessions_api, "generation_runner", _Runner())
    monkeypatch.setattr(sessions_api, "job_store", GenerationJobStore(tmp_path / "jobs"))
    client = TestClient(app)
    session_resp = client.post("/api/v1/sessions", json={"title": "修复测试"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    resp = client.post(f"/api/v1/sessions/{session_id}/generation/jobs/job-missing/fix/skip")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"
