import httpx
from fastapi.testclient import TestClient

from app.api.v1 import settings as settings_api
from app.main import app
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
            "base_url": "https://gateway.public-gateway.dev/v1",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "valid": True,
        "message": "OpenAI API Key \u9a8c\u8bc1\u6210\u529f",
    }
    assert seen["url_policy"] == "https_domain_only"
    assert seen["requested_url"] == "https://gateway.public-gateway.dev/v1/models"


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
    assert (
        "\u4ec5\u652f\u6301\u4f7f\u7528 https \u7684\u57df\u540d\u5730\u5740"
        "\u8fdb\u884c\u6821\u9a8c"
    ) in body["message"]
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
    assert (
        "\u4ec5\u652f\u6301\u4f7f\u7528 https \u7684\u57df\u540d\u5730\u5740"
        "\u8fdb\u884c\u6821\u9a8c"
    ) in body["message"]
    assert "http://gateway.example.com/v1/models" in body["message"]


def test_validate_openai_rejects_private_use_hostname_suffix(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("transport should not be called for blocked URLs")

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "https://proxy.internal/v1",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert (
        "\u4ec5\u652f\u6301\u4f7f\u7528 https \u7684\u57df\u540d\u5730\u5740"
        "\u8fdb\u884c\u6821\u9a8c"
    ) in body["message"]
    assert "proxy.internal" in body["message"]


def test_validate_google_sends_api_key_in_header(monkeypatch):
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["requested_url"] = str(request.url)
        seen["api_key_header"] = request.headers.get("x-goog-api-key")
        return httpx.Response(200, json={"models": []})

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "google",
            "api_key": "google-secret-key",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["message"].startswith("Google API Key")
    assert seen["requested_url"] == "https://generativelanguage.googleapis.com/v1beta/models"
    assert seen["api_key_header"] == "google-secret-key"


def test_validate_google_network_errors_do_not_leak_url_or_key(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    _install_mock_client(monkeypatch, handler)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/settings/validate",
        json={
            "provider": "google",
            "api_key": "google-secret-key",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["message"].startswith(settings_api._NETWORK_ERROR_PREFIX)
    assert "google-secret-key" not in body["message"]
    assert "generativelanguage.googleapis.com" not in body["message"]


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
            "base_url": "https://gateway.public-gateway.dev/v1",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "valid": False,
        "message": "API Key \u65e0\u6548",
    }
