from __future__ import annotations

import asyncio
import inspect
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar, cast, get_type_hints

from pydantic import BaseModel, Field

from .background import BackgroundManager
from .skills import SkillCatalog
from .subagents import SubagentManager
from .tasks import TaskManager, TaskStatus
from .todo import TodoManager
from .types import ToolCall, ToolResult


HandlerResult = Any
ToolHandler = Callable[..., Awaitable[HandlerResult] | HandlerResult]
DecoratedTool = TypeVar("DecoratedTool", bound=ToolHandler)


class ToolExecutionError(Exception):
    def __init__(self, message: str, *, content: dict[str, Any] | None = None):
        super().__init__(message)
        self.content = content or {"error": message}


@dataclass(slots=True)
class BashPolicy:
    workspace_root: Path
    allowlist_prefixes: tuple[str, ...] = (
        "pwd",
        "ls",
        "echo",
        "cat",
        "head",
        "tail",
        "sed",
        "rg",
        "find",
        "python",
        "python3",
        "pytest",
        "git",
    )
    permissive_mode: bool = False

    def validate(self, command: str, working_directory: Path) -> None:
        _ensure_within_root(working_directory, self.workspace_root)
        if self.permissive_mode:
            return
        parts = shlex.split(command)
        if not parts:
            raise ValueError("Command must not be empty.")
        if parts[0] not in self.allowlist_prefixes:
            raise ValueError(f"Command prefix '{parts[0]}' is not allowed in restricted mode.")


@dataclass(slots=True)
class ReadPolicy:
    workspace_root: Path
    permissive_mode: bool = False

    def resolve(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        if not self.permissive_mode:
            _ensure_within_root(candidate, self.workspace_root)
        return candidate.resolve()


@dataclass(slots=True)
class ToolContext:
    workspace_root: Path
    bash_policy: BashPolicy
    read_policy: ReadPolicy
    todo_manager: TodoManager | None = None
    skill_catalog: SkillCatalog | None = None
    task_manager: TaskManager | None = None
    subagent_manager: SubagentManager | None = None
    background_manager: BackgroundManager | None = None
    active_skills: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    source: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_model.model_json_schema(),
        }


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool_definition: Tool | ToolHandler) -> Tool:
        if isinstance(tool_definition, Tool):
            tool = tool_definition
        else:
            tool = getattr(tool_definition, "__agentloop_tool__", None)
            if tool is None:
                raise TypeError("Expected Tool instance or function decorated with @tool.")
        self.tools[tool.name] = tool
        return tool

    def extend(self, tool_definitions: list[Tool | ToolHandler]) -> None:
        for tool_definition in tool_definitions:
            self.register(tool_definition)

    def to_model_tools(self) -> list[dict[str, Any]]:
        return [tool.to_model_tool() for tool in self.tools.values()]

    async def dispatch(self, tool_calls: list[ToolCall], context: ToolContext) -> list[ToolResult]:
        results: list[ToolResult] = []
        for tool_call in tool_calls:
            tool = self.tools.get(tool_call.tool_name)
            if tool is None:
                results.append(
                    ToolResult(
                        tool_name=tool_call.tool_name,
                        tool_call_id=tool_call.tool_call_id,
                        content={"error": f"Unknown tool: {tool_call.tool_name}"},
                        is_error=True,
                    )
                )
                continue
            try:
                args = tool.args_model.model_validate(tool_call.args)
            except Exception as exc:
                results.append(
                    ToolResult(
                        tool_name=tool_call.tool_name,
                        tool_call_id=tool_call.tool_call_id,
                        content={"error": f"Invalid arguments: {exc}"},
                        is_error=True,
                    )
                )
                continue
            try:
                content = await _invoke_tool(tool.handler, args, context)
                if isinstance(content, ToolResult):
                    results.append(content)
                else:
                    results.append(
                        ToolResult(
                            tool_name=tool_call.tool_name,
                            tool_call_id=tool_call.tool_call_id,
                            content=_normalize_content(content),
                        )
                    )
            except Exception as exc:
                if isinstance(exc, ToolExecutionError):
                    content = _normalize_content(exc.content)
                else:
                    content = {"error": f"{type(exc).__name__}: {exc}"}
                results.append(
                    ToolResult(
                        tool_name=tool_call.tool_name,
                        tool_call_id=tool_call.tool_call_id,
                        content=content,
                        is_error=True,
                    )
                )
        return results


def tool(
    *,
    name: str | None = None,
    description: str,
) -> Callable[[DecoratedTool], DecoratedTool]:
    def decorator(func: DecoratedTool) -> DecoratedTool:
        resolved_name = name or func.__name__
        args_model = _resolve_args_model(func)
        tool_definition = Tool(
            name=resolved_name,
            description=description,
            args_model=args_model,
            handler=func,
        )
        setattr(func, "__agentloop_tool__", tool_definition)
        return func

    return decorator


def _resolve_args_model(func: ToolHandler) -> type[BaseModel]:
    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    if not parameters:
        raise TypeError("Tool functions must accept at least one Pydantic args parameter.")
    type_hints = get_type_hints(func)
    args_annotation = type_hints.get(parameters[0].name, parameters[0].annotation)
    if not inspect.isclass(args_annotation) or not issubclass(args_annotation, BaseModel):
        raise TypeError("The first tool parameter must be a Pydantic BaseModel subclass.")
    return cast(type[BaseModel], args_annotation)


async def _invoke_tool(handler: ToolHandler, args: BaseModel, context: ToolContext) -> Any:
    signature = inspect.signature(handler)
    if len(signature.parameters) > 1:
        result = handler(args, context)
    else:
        result = handler(args)
    if inspect.isawaitable(result):
        return await cast(Awaitable[Any], result)
    return result


def _ensure_within_root(candidate: Path, root: Path) -> None:
    resolved_candidate = candidate.resolve()
    resolved_root = root.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path '{resolved_candidate}' escapes workspace root '{resolved_root}'.") from exc


def _normalize_content(content: Any) -> Any:
    if isinstance(content, BaseModel):
        return json.loads(content.model_dump_json())
    return content


class BashArgs(BaseModel):
    command: str = Field(description="Shell command to execute.")
    working_directory: str | None = Field(
        default=None,
        description="Optional working directory. Defaults to the agent workspace root.",
    )
    timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0)


class ReadArgs(BaseModel):
    path: str = Field(description="Path to the file to read.")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description="Optional maximum number of lines to return.",
    )


class ReadSkillResourceArgs(BaseModel):
    skill_name: str = Field(description="Name of the already activated skill to read from.")
    path: str = Field(description="Relative resource path inside the skill, for example references/foo.md.")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description="Optional maximum number of lines to return.",
    )


class WriteFileArgs(BaseModel):
    path: str = Field(description="Path to the file to create or overwrite.")
    content: str = Field(description="Complete file contents to write.")


class EditFileArgs(BaseModel):
    path: str = Field(description="Path to the file to edit.")
    old_text: str = Field(description="Exact text to replace.")
    new_text: str = Field(description="Replacement text.")


class TodoItemArgs(BaseModel):
    id: int = Field(description="Stable task identifier.")
    text: str = Field(description="Task description.")
    status: str = Field(default="pending", description="One of pending, in_progress, done.")


class TodoArgs(BaseModel):
    items: list[TodoItemArgs] = Field(description="Complete todo list state.")


class LoadSkillArgs(BaseModel):
    name: str = Field(description="Name of the skill to load.")


class TaskCreateArgs(BaseModel):
    title: str = Field(description="Task title.")
    task_id: str | None = Field(default=None, description="Optional stable task id.")
    dependencies: list[str] = Field(default_factory=list, description="Task ids that must be done first.")
    summary: str = Field(default="", description="Optional task summary.")


class TaskUpdateArgs(BaseModel):
    task_id: str = Field(description="Task id to update.")
    title: str | None = Field(default=None, description="Optional new task title.")
    status: TaskStatus | None = Field(default=None, description="Optional new task status.")
    dependencies: list[str] | None = Field(default=None, description="Optional replacement dependency list.")
    summary: str | None = Field(default=None, description="Optional replacement summary.")
    note: str | None = Field(default=None, description="Optional note to append or replace.")
    replace_notes: bool = Field(default=False, description="Whether to replace existing notes instead of appending.")


class TaskUseArgs(BaseModel):
    task_id: str = Field(description="Task id to use as the current task.")


class TaskListArgs(BaseModel):
    include_notes: bool = Field(default=False, description="Whether to include task notes in the response.")


class SubagentRunArgs(BaseModel):
    task: str = Field(description="Delegated subtask for the subagent.")
    context: str | None = Field(default=None, description="Optional supporting context for the subagent.")
    allowed_tools: list[str] | None = Field(default=None, description="Optional explicit tool allowlist.")
    max_turns: int | None = Field(default=None, ge=1, le=12, description="Optional max turns for the subagent.")


class BackgroundRunArgs(BaseModel):
    command: str = Field(description="Shell command to run in the background.")
    working_directory: str | None = Field(default=None, description="Optional working directory inside the workspace.")
    timeout_seconds: float = Field(default=300.0, ge=0.1, le=3600.0)


class BackgroundSubagentArgs(BaseModel):
    task: str = Field(description="Delegated subtask to run in the background.")
    context: str | None = Field(default=None, description="Optional supporting context for the background subagent.")
    allowed_tools: list[str] | None = Field(default=None, description="Optional explicit tool allowlist for the background subagent.")
    max_turns: int | None = Field(default=None, ge=1, le=12, description="Optional max turns for the background subagent.")


class BackgroundCheckArgs(BaseModel):
    task_id: str | None = Field(default=None, description="Optional specific background task id to inspect.")


@tool(name="bash", description="Run a shell command inside the workspace.")
async def bash(args: BashArgs, context: ToolContext) -> dict[str, Any]:
    working_directory = context.workspace_root if args.working_directory is None else Path(args.working_directory)
    if not working_directory.is_absolute():
        working_directory = context.workspace_root / working_directory
    context.bash_policy.validate(args.command, working_directory.resolve())
    process = await asyncio.create_subprocess_shell(
        args.command,
        cwd=str(working_directory.resolve()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=args.timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"Command timed out after {args.timeout_seconds} seconds.") from exc
    return {
        "returncode": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "working_directory": str(working_directory.resolve()),
    }


@tool(name="read_file", description="Read a text file from the workspace.")
def read_file(args: ReadArgs, context: ToolContext) -> dict[str, Any]:
    path = context.read_policy.resolve(args.path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    truncated = False
    if args.limit is not None and len(lines) > args.limit:
        lines = lines[: args.limit]
        truncated = True
    content = "\n".join(lines)
    return {
        "path": str(path),
        "content": content,
        "truncated": truncated,
    }


@tool(
    name="read_skill_resource",
    description="Read a file from references/, scripts/, or assets/ of an already activated skill.",
)
def read_skill_resource(args: ReadSkillResourceArgs, context: ToolContext) -> dict[str, Any]:
    if context.skill_catalog is None:
        raise ValueError("Skill catalog is not available in this context.")
    skill_name = str(args.skill_name or "").strip()
    if not skill_name:
        raise ValueError("skill_name is required.")
    if skill_name not in context.active_skills:
        raise ValueError(f"Skill '{skill_name}' is not active. Load it first with load_skill.")
    record = context.skill_catalog.records.get(skill_name)
    if record is None:
        raise ValueError(f"Unknown skill: {skill_name}")
    relative_path = Path(str(args.path or "").strip())
    if not str(relative_path):
        raise ValueError("path is required.")
    if relative_path.is_absolute():
        raise ValueError("Use a skill-relative path such as references/foo.md, not an absolute path.")
    if relative_path.parts[0] not in {"references", "scripts", "assets"}:
        raise ValueError("Skill resources must live under references/, scripts/, or assets/.")
    candidate = (record.skill_dir / relative_path).resolve()
    try:
        candidate.relative_to(record.skill_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Skill resource '{relative_path}' escapes skill root '{record.skill_dir}'.") from exc
    if not candidate.exists():
        raise FileNotFoundError(f"No such skill resource: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"Skill resource is not a file: {candidate}")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    truncated = False
    if args.limit is not None and len(lines) > args.limit:
        lines = lines[: args.limit]
        truncated = True
    return {
        "skill_name": skill_name,
        "path": str(relative_path),
        "full_path": str(candidate),
        "content": "\n".join(lines),
        "truncated": truncated,
    }


@tool(name="write_file", description="Create or overwrite a text file in the workspace.")
def write_file(args: WriteFileArgs, context: ToolContext) -> dict[str, Any]:
    path = context.read_policy.resolve(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.content, encoding="utf-8")
    return {
        "path": str(path),
        "chars_written": len(args.content),
        "bytes_written": len(args.content.encode("utf-8")),
    }


@tool(name="edit_file", description="Replace one exact text match inside a workspace file.")
def edit_file(args: EditFileArgs, context: ToolContext) -> dict[str, Any]:
    path = context.read_policy.resolve(args.path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    occurrences = text.count(args.old_text)
    if occurrences == 0:
        raise ValueError("old_text was not found in the file.")
    if occurrences > 1:
        raise ValueError("old_text matched multiple locations; edit_file requires exactly one match.")
    updated = text.replace(args.old_text, args.new_text, 1)
    path.write_text(updated, encoding="utf-8")
    return {
        "path": str(path),
        "replacements": 1,
    }


@tool(name="todo", description="Create or update the current task plan.")
def todo(args: TodoArgs, context: ToolContext) -> dict[str, object]:
    if context.todo_manager is None:
        raise ValueError("Todo manager is not available in this context.")
    return context.todo_manager.update([item.model_dump(mode="python") for item in args.items])


@tool(name="load_skill", description="Load the full instructions for a discovered skill.")
def load_skill(args: LoadSkillArgs, context: ToolContext) -> dict[str, object]:
    if context.skill_catalog is None:
        raise ValueError("Skill catalog is not available in this context.")
    if args.name not in context.skill_catalog.records:
        raise ValueError(f"Unknown skill: {args.name}")
    if args.name not in context.active_skills:
        context.active_skills.append(args.name)
    record = context.skill_catalog.records[args.name]
    return {
        "name": record.name,
        "description": record.description,
        "content": context.skill_catalog.render_skill_content(args.name),
    }


@tool(name="task_list", description="List project tasks and the current task.")
def task_list(args: TaskListArgs, context: ToolContext) -> dict[str, object]:
    if context.task_manager is None:
        raise ValueError("Task manager is not available in this context.")
    tasks = context.task_manager.list_tasks()
    if args.include_notes:
        for task in tasks:
            task["notes"] = list(context.task_manager.require_task(str(task["id"])).notes)
    return {
        "current_task_id": context.task_manager.current_task_id,
        "tasks": tasks,
    }


@tool(name="task_create", description="Create a new persistent project task.")
def task_create(args: TaskCreateArgs, context: ToolContext) -> dict[str, object]:
    if context.task_manager is None:
        raise ValueError("Task manager is not available in this context.")
    record = context.task_manager.create_task(
        title=args.title,
        task_id=args.task_id,
        dependencies=list(args.dependencies),
        summary=args.summary,
    )
    task = next(task for task in context.task_manager.list_tasks() if task["id"] == record.id)
    return {
        "task": task,
        "current_task_id": context.task_manager.current_task_id,
    }


@tool(name="task_update", description="Update a persistent project task.")
def task_update(args: TaskUpdateArgs, context: ToolContext) -> dict[str, object]:
    if context.task_manager is None:
        raise ValueError("Task manager is not available in this context.")
    record = context.task_manager.update_task(
        args.task_id,
        title=args.title,
        status=args.status,
        dependencies=args.dependencies,
        summary=args.summary,
        note=args.note,
        replace_notes=args.replace_notes,
    )
    return {
        "task": next(task for task in context.task_manager.list_tasks() if task["id"] == record.id),
        "current_task_id": context.task_manager.current_task_id,
    }


@tool(name="task_use", description="Switch the current project task.")
def task_use(args: TaskUseArgs, context: ToolContext) -> dict[str, object]:
    if context.task_manager is None:
        raise ValueError("Task manager is not available in this context.")
    record = context.task_manager.use_task(args.task_id)
    return {
        "current_task_id": record.id,
        "task": next(task for task in context.task_manager.list_tasks() if task["id"] == record.id),
    }


@tool(name="subagent_run", description="Delegate a focused subtask to an isolated subagent and wait for the result.")
async def subagent_run(args: SubagentRunArgs, context: ToolContext) -> dict[str, object]:
    if context.subagent_manager is None:
        raise ValueError("Subagent manager is not available in this context.")
    return await context.subagent_manager.run(
        task=args.task,
        context=args.context,
        allowed_tools=args.allowed_tools,
        max_turns=args.max_turns,
    )


@tool(name="background_run", description="Run a shell command in the background and continue working.")
def background_run(args: BackgroundRunArgs, context: ToolContext) -> dict[str, object]:
    if context.background_manager is None:
        raise ValueError("Background manager is not available in this context.")
    working_directory = context.workspace_root if args.working_directory is None else Path(args.working_directory)
    if not working_directory.is_absolute():
        working_directory = context.workspace_root / working_directory
    task_id = context.background_manager.run_command(
        command=args.command,
        working_directory=working_directory.resolve(),
        timeout_seconds=args.timeout_seconds,
    )
    return {
        "task_id": task_id,
        "kind": "command",
        "status": "running",
    }


@tool(name="background_subagent", description="Run a delegated subagent in the background and continue working.")
def background_subagent(args: BackgroundSubagentArgs, context: ToolContext) -> dict[str, object]:
    if context.background_manager is None:
        raise ValueError("Background manager is not available in this context.")
    task_id = context.background_manager.run_subagent(
        task=args.task,
        context=args.context,
        allowed_tools=args.allowed_tools,
        max_turns=args.max_turns,
    )
    return {
        "task_id": task_id,
        "kind": "subagent",
        "status": "running",
    }


@tool(name="background_check", description="Inspect background task status and completed results.")
def background_check(args: BackgroundCheckArgs, context: ToolContext) -> dict[str, object]:
    if context.background_manager is None:
        raise ValueError("Background manager is not available in this context.")
    tasks = context.background_manager.check(args.task_id)
    return {
        "tasks": tasks,
    }


def create_builtin_registry(workspace_root: Path, permissive_mode: bool = False) -> ToolRegistry:
    registry = ToolRegistry()
    registry.extend(
        [
            bash,
            read_file,
            read_skill_resource,
            write_file,
            edit_file,
            todo,
            load_skill,
            task_list,
            task_create,
            task_update,
            task_use,
            subagent_run,
            background_run,
            background_subagent,
            background_check,
        ]
    )
    return registry


def default_tool_context(workspace_root: Path, permissive_mode: bool = False) -> ToolContext:
    root = workspace_root.resolve()
    return ToolContext(
        workspace_root=root,
        bash_policy=BashPolicy(workspace_root=root, permissive_mode=permissive_mode),
        read_policy=ReadPolicy(workspace_root=root, permissive_mode=permissive_mode),
    )
