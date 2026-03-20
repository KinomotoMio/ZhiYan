"""Thin CLI for generation smoke tests."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.services.sessions.workspace import DEFAULT_WORKSPACE_ID, WORKSPACE_HEADER

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30.0
_TERMINAL_SUCCESS_TYPES = {"job_completed", "job_waiting_fix_review"}
_TERMINAL_FAILURE_TYPES = {"job_failed", "job_cancelled"}
_TERMINAL_TYPES = _TERMINAL_SUCCESS_TYPES | _TERMINAL_FAILURE_TYPES


class CliError(RuntimeError):
    """Raised for CLI-facing errors."""


@dataclass(frozen=True)
class CliContext:
    base_url: str
    workspace_id: str
    timeout_seconds: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zhiyan-cli",
        description="Minimal CLI for settings and generation smoke tests.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("ZHIYAN_BASE_URL", DEFAULT_BASE_URL),
        help="Backend base URL. Defaults to %(default)s.",
    )
    parser.add_argument(
        "--workspace-id",
        default=os.getenv("ZHIYAN_WORKSPACE_ID", DEFAULT_WORKSPACE_ID),
        help="Workspace header value for local/dev usage.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_env_float("ZHIYAN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        help="HTTP timeout in seconds. Defaults to %(default)s.",
    )

    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser("config", help="Show or update remote settings.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_subparsers.add_parser("show", help="Fetch current settings.")

    config_set_parser = config_subparsers.add_parser(
        "set",
        help="Update settings with KEY=VALUE assignments.",
    )
    config_set_parser.add_argument("assignments", nargs="+", help="Assignments like default_model=openai:gpt-4o-mini")

    create_parser = subparsers.add_parser("create", help="Create a generation job.")
    create_parser.add_argument("--topic", default="", help="Generation topic.")
    create_parser.add_argument("--content", default="", help="Generation content.")
    create_parser.add_argument("--session-id", default=None, help="Existing session id.")
    create_parser.add_argument(
        "--source-id",
        dest="source_ids",
        action="append",
        default=[],
        help="Source id to attach. Can be repeated.",
    )
    create_parser.add_argument("--template-id", default=None, help="Template id.")
    create_parser.add_argument("--num-pages", type=int, default=5, help="Requested page count.")
    create_parser.add_argument(
        "--mode",
        choices=("auto", "review_outline"),
        default="auto",
        help="Generation mode.",
    )
    create_parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the created job until a terminal or review-waiting state.",
    )

    watch_parser = subparsers.add_parser("watch", help="Watch a generation job SSE stream.")
    watch_parser.add_argument("job_id", help="Generation job id.")
    watch_parser.add_argument(
        "--after-seq",
        type=int,
        default=0,
        help="Replay only events after this sequence number.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    context = CliContext(
        base_url=str(args.base_url).rstrip("/"),
        workspace_id=str(args.workspace_id).strip() or DEFAULT_WORKSPACE_ID,
        timeout_seconds=max(0.1, float(args.timeout)),
    )

    try:
        with _make_client(context) as client:
            if args.command == "config":
                return _run_config(client, context, args)
            if args.command == "create":
                return _run_create(client, args)
            if args.command == "watch":
                return _run_watch(client, args.job_id, args.after_seq)
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _run_config(
    client: httpx.Client,
    context: CliContext,
    args: argparse.Namespace,
) -> int:
    if not getattr(args, "config_command", None):
        raise CliError("config requires a subcommand: show or set")

    if args.config_command == "show":
        settings_payload = _request_json(client, "GET", "/api/v1/settings")
    elif args.config_command == "set":
        payload = {key: _parse_assignment_value(raw_value) for key, raw_value in _parse_assignments(args.assignments).items()}
        settings_payload = _request_json(client, "PUT", "/api/v1/settings", json_body=payload)
    else:
        raise CliError(f"unknown config command: {args.config_command}")

    _print_json(
        {
            "base_url": context.base_url,
            "workspace_id": context.workspace_id,
            "settings": settings_payload,
        }
    )
    return 0


def _run_create(client: httpx.Client, args: argparse.Namespace) -> int:
    payload = {
        "topic": args.topic,
        "content": args.content,
        "session_id": args.session_id,
        "source_ids": args.source_ids,
        "template_id": args.template_id,
        "num_pages": args.num_pages,
        "mode": args.mode,
    }
    created = _request_json(client, "POST", "/api/v2/generation/jobs", json_body=payload)
    if not args.watch:
        _print_json(created)
        return 0

    summary = _watch_job(client, str(created["job_id"]), after_seq=0)
    _print_json({"created": created, "watch": summary})
    return _watch_exit_code(summary)


def _run_watch(client: httpx.Client, job_id: str, after_seq: int) -> int:
    summary = _watch_job(client, job_id, after_seq=after_seq)
    _print_json(summary)
    return _watch_exit_code(summary)


def _watch_job(client: httpx.Client, job_id: str, *, after_seq: int) -> dict[str, Any]:
    path = f"/api/v2/generation/jobs/{job_id}/events"
    if after_seq > 0:
        path = f"{path}?{urlencode({'after_seq': after_seq})}"

    last_seq = max(0, int(after_seq))
    done_received = False
    event_count = 0
    last_event: dict[str, Any] | None = None
    terminal_event: dict[str, Any] | None = None

    with client.stream("GET", path) as response:
        _raise_for_response(response)

        for line in response.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue

            data = line[6:].strip()
            if not data:
                continue
            if data == "[DONE]":
                done_received = True
                break

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            if isinstance(event.get("seq"), int):
                last_seq = max(last_seq, int(event["seq"]))
            event_type = str(event.get("type") or "")
            if event_type != "heartbeat":
                event_count += 1
                last_event = event
            if event_type in _TERMINAL_TYPES:
                terminal_event = event

    return {
        "job_id": job_id,
        "events_seen": event_count,
        "last_seq": last_seq,
        "done_received": done_received,
        "terminal_event": terminal_event,
        "last_event": last_event,
    }


def _watch_exit_code(summary: dict[str, Any]) -> int:
    terminal_event = summary.get("terminal_event")
    event_type = ""
    if isinstance(terminal_event, dict):
        event_type = str(terminal_event.get("type") or "")
    if event_type in _TERMINAL_FAILURE_TYPES:
        return 1
    return 0


def _make_client(context: CliContext) -> httpx.Client:
    return httpx.Client(
        base_url=context.base_url,
        timeout=context.timeout_seconds,
        headers={
            WORKSPACE_HEADER: context.workspace_id,
            "Accept": "application/json",
        },
    )


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request(method, path, json=json_body)
    _raise_for_response(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise CliError(f"{method} {path} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{method} {path} returned unexpected payload type")
    return payload


def _raise_for_response(response: httpx.Response) -> None:
    if response.is_success:
        return

    message = response.reason_phrase or f"HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        if text:
            message = text
    else:
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message")
            if isinstance(detail, str) and detail.strip():
                message = detail.strip()
    raise CliError(f"{response.request.method} {response.request.url.path}: {message}")


def _parse_assignments(assignments: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise CliError(f"invalid assignment: {assignment!r}; expected KEY=VALUE")
        key, raw_value = assignment.split("=", 1)
        key = key.strip()
        if not key:
            raise CliError(f"invalid assignment: {assignment!r}; missing key")
        parsed[key] = raw_value
    return parsed


def _parse_assignment_value(value: str) -> Any:
    candidate = value.strip()
    if not candidate:
        return ""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return value


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
