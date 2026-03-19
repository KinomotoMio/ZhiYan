import asyncio

import pytest
from app.utils import security


def test_https_domain_only_allows_openai_domain():
    assert asyncio.run(
        security.is_safe_url(
            "https://api.openai.com/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_allows_custom_gateway_domain():
    assert asyncio.run(
        security.is_safe_url(
            "https://gateway.public-gateway.dev/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_rejects_http_scheme():
    assert not asyncio.run(
        security.is_safe_url(
            "http://gateway.example.com/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_rejects_localhost():
    assert not asyncio.run(
        security.is_safe_url(
            "https://localhost:8000/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_rejects_ip_literal():
    assert not asyncio.run(
        security.is_safe_url(
            "https://127.0.0.1:8000/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_does_not_use_resolved_ip_policy(monkeypatch):
    async def fail_if_called(url: str) -> bool:  # noqa: ARG001
        raise AssertionError("resolved_ip policy should not run")

    monkeypatch.setattr(security, "_allows_resolved_ip", fail_if_called)

    assert asyncio.run(
        security.is_safe_url(
            "https://api.openai.com/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_rejects_private_use_hostname_suffix():
    assert not asyncio.run(
        security.is_safe_url(
            "https://api.gateway.internal/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_https_domain_only_rejects_embedded_credentials():
    assert not asyncio.run(
        security.is_safe_url(
            "https://user:secret@gateway.public-gateway.dev/v1/models",
            url_policy="https_domain_only",
        )
    )


def test_sanitize_upload_filename_allows_plain_filename():
    assert security.sanitize_upload_filename("deck-v1.pptx") == "deck-v1.pptx"


@pytest.mark.parametrize(
    "filename",
    [
        "../../evil.txt",
        "..\\..\\evil.txt",
        "/tmp/evil.txt",
        "C:/Users/Public/evil.txt",
        "C:\\Users\\Public\\evil.txt",
        "..",
        ".",
        "",
    ],
)
def test_sanitize_upload_filename_rejects_path_traversal(filename: str):
    with pytest.raises(ValueError):
        security.sanitize_upload_filename(filename)


def test_build_safe_upload_path_stays_inside_upload_root(tmp_path):
    file_dir = tmp_path / "uploads" / "src-1"
    file_dir.mkdir(parents=True)

    safe_path = security.build_safe_upload_path(file_dir, "report.pdf")

    assert safe_path.parent == file_dir.resolve()
    assert safe_path.name == "report.pdf"
    assert file_dir.resolve() in safe_path.parents
