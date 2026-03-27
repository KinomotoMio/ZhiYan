from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .builder import AgentBuilder
from .skills import SkillCatalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentloop", description="Hand-rolled Python agent loop.")
    parser.add_argument(
        "--project-root",
        default=os.getenv("AGENTLOOP_PROJECT_ROOT", os.getcwd()),
        help="Project root used for tools, skills, and MCP config discovery.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("AGENTLOOP_MODEL"),
        help="LiteLLM model identifier.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=_env_float("AGENTLOOP_TEMPERATURE"),
        help="Optional model temperature.",
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("AGENTLOOP_API_BASE"),
        help="Optional LiteLLM api_base override.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("AGENTLOOP_API_KEY"),
        help="Optional LiteLLM api_key override.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=int(os.getenv("AGENTLOOP_MAX_TURNS", "8")),
        help="Maximum agent turns.",
    )
    parser.add_argument(
        "--compact-token-threshold",
        type=int,
        default=int(os.getenv("AGENTLOOP_COMPACT_TOKEN_THRESHOLD", "6000")),
        help="Automatic compact threshold based on LiteLLM usage tokens.",
    )
    parser.add_argument(
        "--compact-tail-turns",
        type=int,
        default=int(os.getenv("AGENTLOOP_COMPACT_TAIL_TURNS", "2")),
        help="Number of recent raw turns to retain after compact.",
    )
    parser.add_argument(
        "--no-auto-compact",
        action="store_true",
        default=not _env_bool("AGENTLOOP_AUTO_COMPACT", True),
        help="Disable automatic compaction based on token usage.",
    )
    parser.add_argument(
        "--permissive-tools",
        action="store_true",
        default=_env_flag("AGENTLOOP_PERMISSIVE_TOOLS"),
        help="Relax built-in tool restrictions for testing and demos.",
    )

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a one-shot agent invocation.")
    run_parser.add_argument("--prompt", required=True, help="User prompt.")
    run_parser.add_argument(
        "--skill",
        dest="skills",
        action="append",
        default=[],
        help="Explicitly activate a discovered skill by name.",
    )

    chat_parser = subparsers.add_parser("chat", help="Open a minimal interactive REPL.")
    chat_parser.add_argument(
        "--skill",
        dest="skills",
        action="append",
        default=[],
        help="Explicitly activate a discovered skill before chat begins.",
    )
    chat_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show extra event details for each chat turn.",
    )
    chat_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON results instead of human-readable chat output.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect tools, skills, and MCP config.")
    inspect_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    smoke_parser = subparsers.add_parser("smoke-live", help="Run a real-model smoke test.")
    smoke_parser.add_argument(
        "--prompt",
        default="Use the read tool to read README.md and reply with only the first line.",
        help="Smoke test prompt.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=False)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    builder = _builder_from_args(args)
    if args.command == "inspect":
        payload = builder.inspect()
        print(json.dumps(payload, ensure_ascii=True, indent=2 if args.pretty else None))
        return 0

    if args.model is None:
        print("Error: --model or AGENTLOOP_MODEL is required for model-backed commands.", file=sys.stderr)
        return 2

    agent = builder.build()
    if args.command == "run":
        result = asyncio.run(agent.run(args.prompt, activate_skills=args.skills))
        print(json.dumps(_result_to_json(result), ensure_ascii=True))
        return 0 if result.stop_reason == "completed" else 1
    if args.command == "chat":
        return _run_chat(
            agent,
            builder.skill_catalog,
            args.skills,
            json_mode=bool(args.json),
            debug=bool(args.debug),
        )
    if args.command == "smoke-live":
        result = asyncio.run(agent.run(args.prompt))
        print(json.dumps(_result_to_json(result), ensure_ascii=True))
        return 0 if result.stop_reason == "completed" else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def _builder_from_args(args: argparse.Namespace) -> AgentBuilder:
    builder = AgentBuilder.from_project(Path(args.project_root))
    builder.with_max_turns(args.max_turns)
    builder.with_auto_compact(not args.no_auto_compact)
    builder.with_compact_token_threshold(args.compact_token_threshold)
    builder.with_compact_tail_turns(args.compact_tail_turns)
    builder.with_permissive_tools(args.permissive_tools)
    builder.discover_skills()
    builder.load_mcp_config()
    if getattr(args, "model", None):
        builder.with_litellm(
            model=args.model,
            temperature=args.temperature,
            api_base=args.api_base,
            api_key=args.api_key,
        )
    return builder


def _run_chat(agent, skill_catalog: SkillCatalog | None, skills: list[str], *, json_mode: bool, debug: bool) -> int:
    print("Type 'exit' or 'quit' to stop. Use /help for commands.")
    session = agent.start_session(activate_skills=skills)
    with asyncio.Runner() as runner:
        try:
            while True:
                try:
                    prompt = input("> ").strip()
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print()
                    break
                if not prompt:
                    continue
                if prompt.lower() in {"exit", "quit"}:
                    break
                if prompt.startswith("/"):
                    command = prompt[1:].strip()
                    command_name, _, command_args = command.partition(" ")
                    command_args = command_args.strip() or None
                    if command in {"exit", "quit"}:
                        break
                    if command == "help":
                        _print_chat_help()
                        continue
                    if command == "skills":
                        _print_skill_list(skill_catalog)
                        continue
                    if command == "tasks":
                        if json_mode:
                            print(json.dumps({"tasks": session.tasks, "current_task": session.current_task}, ensure_ascii=True))
                        else:
                            _print_task_list(session.tasks)
                        continue
                    if command.startswith("plan "):
                        result = runner.run(session.plan(command[5:].strip()))
                        if json_mode:
                            print(json.dumps(_result_to_json(result), ensure_ascii=True))
                        else:
                            _print_chat_result(result, debug=debug)
                            _print_todo_summary(session.todo_summary)
                        continue
                    if command == "plan":
                        print(json.dumps({"error": "Usage: /plan <prompt>"}, ensure_ascii=True) if json_mode else "[error] Usage: /plan <prompt>")
                        continue
                    if command == "reset":
                        session.reset()
                        print(json.dumps({"reset": True}, ensure_ascii=True) if json_mode else "[session] reset")
                        continue
                    if command.startswith("task use "):
                        try:
                            task = runner.run(session.use_task(command[9:].strip()))
                        except ValueError as exc:
                            print(json.dumps({"error": str(exc)}, ensure_ascii=True) if json_mode else f"[error] {exc}")
                            continue
                        if json_mode:
                            print(json.dumps({"current_task": task}, ensure_ascii=True))
                        else:
                            print(f"[task] current={task['id']} status={task['status']} title={task['title']}")
                        continue
                    if command == "compact":
                        compact_result = runner.run(session.compact())
                        if json_mode:
                            print(json.dumps(_compact_result_to_json(compact_result), ensure_ascii=True))
                        else:
                            print(
                                f"[compact] generation={compact_result.generation} retained_turns={compact_result.retained_turns} "
                                f"messages={compact_result.message_count}"
                            )
                            if debug:
                                print(f"[debug] compact={json.dumps(_compact_result_to_json(compact_result), ensure_ascii=True)}")
                        continue
                    try:
                        result = runner.run(session.invoke_skill(command_name, prompt=command_args))
                    except KeyboardInterrupt:
                        print()
                        break
                    if json_mode:
                        print(json.dumps(_result_to_json(result), ensure_ascii=True))
                    else:
                        if result.stop_reason == "invalid-skill" and result.error:
                            print(f"[error] {result.error}")
                        else:
                            _print_chat_result(
                                result,
                                debug=debug,
                                suppress_tool_names=set() if debug else {"load_skill"},
                            )
                    continue
                try:
                    result = runner.run(session.send(prompt))
                except KeyboardInterrupt:
                    print()
                    break
                if json_mode:
                    print(json.dumps(_result_to_json(result), ensure_ascii=True))
                else:
                    _print_chat_result(result, debug=debug)
        finally:
            runner.run(_drain_litellm_logging_worker())
    return 0


async def _drain_litellm_logging_worker() -> None:
    try:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
    except Exception:
        return

    queue = getattr(GLOBAL_LOGGING_WORKER, "_queue", None)
    if queue is not None:
        try:
            # LiteLLM's flush() only waits when the queue is non-empty, but Ctrl+C can
            # arrive after an item has been dequeued and before its logging task completes.
            await queue.join()
        except Exception:
            pass

    flush = getattr(GLOBAL_LOGGING_WORKER, "flush", None)
    clear_queue = getattr(GLOBAL_LOGGING_WORKER, "clear_queue", None)
    stop = getattr(GLOBAL_LOGGING_WORKER, "stop", None)

    if callable(flush):
        try:
            await flush()
        except Exception:
            pass
    if queue is not None and not queue.empty() and callable(clear_queue):
        try:
            await clear_queue()
        except Exception:
            pass
    running_tasks = list(getattr(GLOBAL_LOGGING_WORKER, "_running_tasks", set()))
    if running_tasks:
        try:
            await asyncio.gather(*running_tasks, return_exceptions=True)
        except Exception:
            pass
    if callable(stop):
        try:
            await stop()
        except Exception:
            pass


def _result_to_json(result) -> dict[str, object]:
    return {
        "output_text": result.output_text,
        "turns": result.turns,
        "stop_reason": result.stop_reason,
        "error": result.error,
        "context_markers": result.context_markers,
        "compact_events": result.compact_events,
        "tool_results": [
            {
                "tool_name": tool_result.tool_name,
                "tool_call_id": tool_result.tool_call_id,
                "content": tool_result.content,
                "is_error": tool_result.is_error,
                "metadata": tool_result.metadata,
            }
            for tool_result in result.tool_results
        ],
    }


def _compact_result_to_json(result) -> dict[str, object]:
    return result.to_dict()


def _env_float(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _print_chat_help() -> None:
    print("Commands:")
    print("/help   Show chat commands and output modes.")
    print("/plan <prompt> Create or update the todo plan for a task.")
    print("/compact Compact older context into a running summary.")
    print("/skills List discovered skills.")
    print("/tasks  List project tasks.")
    print("/task use <id> Switch the current task.")
    print("/reset  Clear conversation history and active skills.")
    print("/exit   Exit the REPL.")
    print("/<name> [args] Invoke a skill. Args override the current target, but session context remains available.")
    print("Flags:")
    print("--debug Show extra event details.")
    print("--json  Print raw JSON results.")


def _print_skill_list(skill_catalog: SkillCatalog | None) -> None:
    if skill_catalog is None or not skill_catalog.records:
        print("No skills discovered.")
        return
    print("Available skills:")
    for skill in sorted(skill_catalog.records.values(), key=lambda item: item.name):
        suffix = f" args: {skill.argument_hint}" if skill.argument_hint else ""
        print(f"- {skill.name}: {skill.description}{suffix}")


def _print_task_list(tasks: list[dict[str, object]]) -> None:
    if not tasks:
        print("No tasks yet.")
        return
    print("Tasks:")
    for task in tasks:
        current = "*" if task.get("current") else "-"
        blocked_by = task.get("blocked_by") or []
        suffix = f" blocked_by={','.join(str(item) for item in blocked_by)}" if blocked_by else ""
        print(f"{current} {task.get('id')}: [{task.get('status')}] {task.get('title')}{suffix}")


def _print_chat_result(result, *, debug: bool, suppress_tool_names: set[str] | None = None) -> None:
    suppressed = suppress_tool_names or set()
    for tool_result in result.tool_results:
        if tool_result.tool_name == "subagent_run" and isinstance(tool_result.content, dict):
            allowed_tools = tool_result.content.get("allowed_tools")
            tools_label = "none" if not allowed_tools else str(len(allowed_tools))
            print(f"[delegate] subagent task={json.dumps(tool_result.content.get('task', ''), ensure_ascii=True)} tools={tools_label}")
        if tool_result.tool_name in suppressed:
            if debug:
                print(_format_tool_summary(tool_result))
                _print_debug_tool_details(tool_result)
            continue
        print(_format_tool_summary(tool_result))
        if debug:
            _print_debug_tool_details(tool_result)
    text = (result.output_text or "").strip("\n")
    if text:
        print(text)
    if result.stop_reason != "completed":
        print(f"[status] stop_reason={result.stop_reason}")
    if result.error:
        print(f"[error] {result.error}")
    if debug:
        for compact_event in result.compact_events:
            print(f"[debug] compact_event={json.dumps(compact_event, ensure_ascii=True)}")
    if debug:
        for marker in result.context_markers:
            print(f"[debug] context_marker={json.dumps(marker, ensure_ascii=True)}")
    if debug:
        print(f"[debug] turns={result.turns} stop_reason={result.stop_reason}")


def _format_tool_summary(tool_result) -> str:
    status = "error" if tool_result.is_error else "ok"
    content = tool_result.content
    if tool_result.is_error:
        return f"[tool:{tool_result.tool_name}] {status} - {_short_error(content)}"
    if tool_result.tool_name == "read_file" and isinstance(content, dict):
        suffix = " truncated" if content.get("truncated") else ""
        return f"[tool:read_file] {status} - path={content.get('path')}{suffix}"
    if tool_result.tool_name == "write_file" and isinstance(content, dict):
        return (
            f"[tool:write_file] {status} - path={content.get('path')} "
            f"chars={content.get('chars_written')} bytes={content.get('bytes_written')}"
        )
    if tool_result.tool_name == "edit_file" and isinstance(content, dict):
        return (
            f"[tool:edit_file] {status} - path={content.get('path')} "
            f"replacements={content.get('replacements')}"
        )
    if tool_result.tool_name == "todo" and isinstance(content, dict):
        counts = content.get("counts", {})
        return (
            f"[tool:todo] {status} - total={counts.get('total', 0)} "
            f"in_progress={counts.get('in_progress', 0)} done={counts.get('done', 0)}"
        )
    if tool_result.tool_name == "task_list" and isinstance(content, dict):
        tasks = content.get("tasks", [])
        return f"[tool:task_list] {status} - total={len(tasks)} current={content.get('current_task_id')}"
    if tool_result.tool_name == "task_create" and isinstance(content, dict):
        task = content.get("task", {})
        return f"[tool:task_create] {status} - id={task.get('id')} status={task.get('status')}"
    if tool_result.tool_name == "task_update" and isinstance(content, dict):
        task = content.get("task", {})
        return f"[tool:task_update] {status} - id={task.get('id')} status={task.get('status')}"
    if tool_result.tool_name == "task_use" and isinstance(content, dict):
        return f"[tool:task_use] {status} - current={content.get('current_task_id')}"
    if tool_result.tool_name == "subagent_run" and isinstance(content, dict):
        return (
            f"[tool:subagent_run] {status} - stop_reason={content.get('stop_reason')} "
            f"turns={content.get('turns')}"
        )
    if tool_result.tool_name == "background_run" and isinstance(content, dict):
        return f"[tool:background_run] {status} - task_id={content.get('task_id')} status={content.get('status')}"
    if tool_result.tool_name == "background_subagent" and isinstance(content, dict):
        return f"[tool:background_subagent] {status} - task_id={content.get('task_id')} status={content.get('status')}"
    if tool_result.tool_name == "background_check" and isinstance(content, dict):
        tasks = content.get("tasks", [])
        return f"[tool:background_check] {status} - total={len(tasks)}"
    if tool_result.tool_name == "load_skill" and isinstance(content, dict):
        return f"[tool:load_skill] {status} - name={content.get('name')}"
    if tool_result.tool_name == "bash" and isinstance(content, dict):
        snippet = _first_meaningful_line(content.get("stdout")) or _first_meaningful_line(content.get("stderr"))
        detail = f" returncode={content.get('returncode')}"
        if content.get("working_directory"):
            detail += f" cwd={content.get('working_directory')}"
        if snippet:
            detail += f" output={snippet}"
        return f"[tool:bash] {status} -{detail}"
    if isinstance(content, dict):
        keys = ", ".join(sorted(str(key) for key in content.keys())[:4])
        if keys:
            return f"[tool:{tool_result.tool_name}] {status} - keys={keys}"
    return f"[tool:{tool_result.tool_name}] {status}"


def _print_debug_tool_details(tool_result) -> None:
    if tool_result.metadata:
        print(f"[debug] metadata={json.dumps(tool_result.metadata, ensure_ascii=True)}")
    content = tool_result.content
    if isinstance(content, dict):
        debug_content = dict(content)
        if "content" in debug_content and isinstance(debug_content["content"], str):
            debug_content["content_preview"] = _truncate(debug_content.pop("content"))
        print(f"[debug] tool_result={json.dumps(debug_content, ensure_ascii=True)}")
    else:
        print(f"[debug] tool_result={json.dumps(content, ensure_ascii=True)}")


def _short_error(content: Any) -> str:
    if isinstance(content, dict) and "error" in content:
        return _truncate(str(content["error"]))
    return _truncate(str(content))


def _first_meaningful_line(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    for line in value.splitlines():
        stripped = line.strip()
        if stripped:
            return _truncate(stripped)
    return None


def _truncate(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _print_todo_summary(summary: str) -> None:
    if summary:
        print(summary)
