import json

import httpx

from app import cli


def _mock_client(context: cli.CliContext, handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(
        transport=transport,
        base_url=context.base_url,
        headers={cli.WORKSPACE_HEADER: context.workspace_id},
    )


def test_cli_config_show_outputs_current_settings(monkeypatch, capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/settings"
        assert request.headers["x-workspace-id"] == "workspace-cli"
        return httpx.Response(
            200,
            json={
                "default_model": "openai:gpt-4o-mini",
                "enable_vision_verification": True,
            },
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(
        ["--base-url", "http://testserver", "--workspace-id", "workspace-cli", "config", "show"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["base_url"] == "http://testserver"
    assert output["workspace_id"] == "workspace-cli"
    assert output["settings"]["default_model"] == "openai:gpt-4o-mini"


def test_cli_config_set_updates_remote_settings(monkeypatch, capsys):
    seen_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        assert request.method == "PUT"
        assert request.url.path == "/api/v1/settings"
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "default_model": "openai:gpt-4o-mini",
                "enable_vision_verification": False,
                "content_type_confidence_threshold": 0.72,
            },
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(
        [
            "config",
            "set",
            "default_model=openai:gpt-4o-mini",
            "enable_vision_verification=false",
            "content_type_confidence_threshold=0.72",
        ]
    )

    assert exit_code == 0
    assert seen_payload == {
        "default_model": "openai:gpt-4o-mini",
        "enable_vision_verification": False,
        "content_type_confidence_threshold": 0.72,
    }
    output = json.loads(capsys.readouterr().out)
    assert output["settings"]["enable_vision_verification"] is False


def test_cli_create_posts_job_payload_and_prints_result(monkeypatch, capsys):
    seen_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        assert request.method == "POST"
        assert request.url.path == "/api/v2/generation/jobs"
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "job_id": "job-cli-1",
                "session_id": "session-cli-1",
                "status": "pending",
                "created_at": "2026-03-21T00:00:00Z",
                "event_stream_url": "/api/v2/generation/jobs/job-cli-1/events",
            },
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(
        [
            "create",
            "--topic",
            "CLI smoke",
            "--content",
            "Use this for smoke testing",
            "--session-id",
            "session-existing",
            "--source-id",
            "src-1",
            "--source-id",
            "src-2",
            "--template-id",
            "tpl-1",
            "--num-pages",
            "7",
            "--mode",
            "review_outline",
        ]
    )

    assert exit_code == 0
    assert seen_payload == {
        "topic": "CLI smoke",
        "content": "Use this for smoke testing",
        "session_id": "session-existing",
        "source_ids": ["src-1", "src-2"],
        "template_id": "tpl-1",
        "num_pages": 7,
        "mode": "review_outline",
    }
    output = json.loads(capsys.readouterr().out)
    assert output["job_id"] == "job-cli-1"


def test_cli_watch_consumes_sse_until_completed(monkeypatch, capsys):
    stream_body = "\n".join(
        [
            'data: {"seq":1,"type":"job_started","job_id":"job-cli-1"}',
            "",
            'data: {"seq":2,"type":"stage_started","job_id":"job-cli-1","stage":"outline"}',
            "",
            'data: {"seq":3,"type":"job_completed","job_id":"job-cli-1"}',
            "",
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v2/generation/jobs/job-cli-1/events"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=stream_body,
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(["watch", "job-cli-1"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["job_id"] == "job-cli-1"
    assert output["done_received"] is True
    assert output["terminal_event"]["type"] == "job_completed"
    assert output["events_seen"] == 3


def test_cli_watch_treats_waiting_fix_review_as_success_terminal(monkeypatch, capsys):
    stream_body = "\n".join(
        [
            'data: {"seq":4,"type":"job_waiting_fix_review","job_id":"job-cli-fix"}',
            "",
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=stream_body,
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(["watch", "job-cli-fix"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["terminal_event"]["type"] == "job_waiting_fix_review"


def test_cli_agentic_delegates_to_embedded_runtime(monkeypatch):
    seen: dict[str, list[str]] = {}

    def fake_run(argv: list[str]) -> int:
        seen["argv"] = list(argv)
        return 0

    monkeypatch.setattr(cli, "_run_agentic", fake_run)

    exit_code = cli.main(["agentic", "--project-root", "/tmp/demo", "inspect"])

    assert exit_code == 0
    assert seen["argv"] == ["--project-root", "/tmp/demo", "inspect"]


def test_cli_slidev_mvp_posts_payload_and_prints_next_steps(monkeypatch, capsys):
    seen_payload: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        assert request.method == "POST"
        assert request.url.path == "/api/v2/generation/slidev-mvp"
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "deck_id": "deck-cli-1",
                "title": "CLI Deck",
                "markdown": "---\\ntheme: default\\n---\\n\\n# Cover\\n",
                "artifact_dir": "/tmp/slidev",
                "slides_path": "/tmp/slidev/slides.md",
                "build_output_dir": "/tmp/slidev/dist",
                "dev_command": "cd /tmp/sandbox && pnpm exec slidev /tmp/slidev/slides.md",
                "build_command": "cd /tmp/sandbox && pnpm exec slidev build /tmp/slidev/slides.md --out /tmp/slidev/dist",
                "validation": {"ok": True},
                "agentic": {"turns": 5},
            },
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(
        [
            "slidev-mvp",
            "--topic",
            "CLI Deck",
            "--content",
            "offline slidev",
            "--session-id",
            "session-cli",
            "--source-id",
            "src-1",
            "--num-pages",
            "6",
            "--build",
        ]
    )

    assert exit_code == 0
    assert seen_payload == {
        "topic": "CLI Deck",
        "content": "offline slidev",
        "session_id": "session-cli",
        "source_ids": ["src-1"],
        "num_pages": 6,
        "build": True,
    }
    output = json.loads(capsys.readouterr().out)
    assert output["deck_id"] == "deck-cli-1"
    assert output["next_steps"] == [
        "Preview locally: cd /tmp/sandbox && pnpm exec slidev /tmp/slidev/slides.md",
        "Build locally: cd /tmp/sandbox && pnpm exec slidev build /tmp/slidev/slides.md --out /tmp/slidev/dist",
    ]


def test_cli_surfaces_non_2xx_errors(monkeypatch, capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"detail": "请先确认大纲后再继续"},
            request=request,
        )

    monkeypatch.setattr(cli, "_make_client", lambda context: _mock_client(context, handler))

    exit_code = cli.main(["watch", "job-error"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "请先确认大纲后再继续" in captured.err
