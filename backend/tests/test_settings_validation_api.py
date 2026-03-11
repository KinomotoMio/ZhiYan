import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import settings as settings_api
from app.utils import security


def _install_mock_client(monkeypatch, handler, seen: dict | None = None):
    def fake_get_safe_httpx_client(*, url_policy="resolved_ip", **kwargs):
        if seen is not None:
            seen["url_policy"] = url_policy
        return security.get_safe_httpx_client(
            url_policy=url_policy,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(settings_api, "get_safe_httpx_client", fake_get_safe_httpx_client)


def test_validate_openai_accepts_https_gateway_without_dns_global_resolution(monkeypatch):
    seen = {}

    async def fail_if_called(url: str) -> bool:  # noqa: ARG001
        raise AssertionError("resolved_ip policy should not run")

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["requested_url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(security, "_allows_resolved_ip", fail_if_called)
    _install_mock_client(monkeypatch, handler, seen)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "https://gateway.example.com/v1",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"valid": True, "message": "OpenAI API Key 验证成功"}
    assert seen["url_policy"] == "https_domain_only"
    assert seen["requested_url"] == "https://gateway.example.com/v1/models"


def test_validate_openai_rejects_ip_literal_base_url(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("transport should not be called for blocked URLs")

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "https://127.0.0.1:8000/v1",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "仅支持使用 https 的域名地址进行校验" in body["message"]
    assert "127.0.0.1:8000" in body["message"]


def test_validate_openai_rejects_http_gateway(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("transport should not be called for blocked URLs")

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "http://gateway.example.com/v1",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "仅支持使用 https 的域名地址进行校验" in body["message"]
    assert "http://gateway.example.com/v1/models" in body["message"]


def test_validate_openai_maps_401_to_invalid_key(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "openai",
            "api_key": "sk-invalid",
            "base_url": "https://gateway.example.com/v1",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"valid": False, "message": "API Key 无效"}
