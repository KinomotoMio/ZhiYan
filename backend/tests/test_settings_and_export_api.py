import json

from fastapi.testclient import TestClient

from app.api.v1 import export as export_api
from app.main import app


def _sample_export_payload() -> dict:
    return {
        "presentation": {
            "presentationId": "pres-1",
            "title": "测试文稿",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "intro-slide",
                    "layoutId": "intro-slide",
                    "contentData": {"title": "封面"},
                    "components": [],
                }
            ],
        }
    }


def test_settings_api_persists_enable_vision_verification(tmp_path, monkeypatch):
    from app.core import settings_store
    from app.core.config import settings

    original_value = settings.enable_vision_verification
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "_SETTINGS_FILE", settings_path)

    client = TestClient(app)

    try:
        resp = client.put(
            "/api/v1/settings",
            json={"enable_vision_verification": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enable_vision_verification"] is False

        assert settings_path.exists()
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["enable_vision_verification"] is False

        get_resp = client.get("/api/v1/settings")
        assert get_resp.status_code == 200
        assert get_resp.json()["enable_vision_verification"] is False
    finally:
        settings.enable_vision_verification = original_value


def test_export_pdf_returns_503_with_manual_install_hint(monkeypatch):
    from app.services.export import pdf_exporter

    async def fake_export_pdf(html_content: str):  # noqa: ARG001
        raise RuntimeError(
            "Playwright Chromium 自动安装失败。安装超时（>90s）。"
            "请手动执行: uv run playwright install chromium"
        )

    monkeypatch.setattr(pdf_exporter, "export_pdf", fake_export_pdf)

    client = TestClient(app)
    resp = client.post("/api/v1/export/pdf", json=_sample_export_payload())

    assert resp.status_code == 503
    assert "uv run playwright install chromium" in resp.json()["detail"]


def test_export_content_disposition_uses_rfc5987_for_non_ascii_title():
    header = export_api._build_content_disposition("测试汇报", "pptx")

    assert 'filename="presentation.pptx"' in header
    assert "filename*=UTF-8''%E6%B5%8B%E8%AF%95%E6%B1%87%E6%8A%A5.pptx" in header
    header.encode("latin-1")


def test_export_pdf_returns_non_ascii_filename_header(monkeypatch):
    from app.services.export import pdf_exporter

    async def fake_export_pdf(html_content: str):  # noqa: ARG001
        return b"%PDF-1.4"

    monkeypatch.setattr(pdf_exporter, "export_pdf", fake_export_pdf)

    client = TestClient(app)
    resp = client.post("/api/v1/export/pdf", json=_sample_export_payload())

    assert resp.status_code == 200
    assert 'filename="presentation.pdf"' in resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]


def test_cors_preflight_allows_localhost_and_loopback():
    client = TestClient(app)

    for origin in ("http://127.0.0.1:3000", "http://localhost:5173"):
        resp = client.options(
            "/api/v1/settings",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type,x-workspace-id",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_rejects_unknown_origin():
    client = TestClient(app)
    resp = client.options(
        "/api/v1/settings",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 400
