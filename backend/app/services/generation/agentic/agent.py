from __future__ import annotations

from html import escape
from dataclasses import dataclass, field, replace
from typing import Any

from .background import BackgroundManager
from .context_policy import ContextMarker, ContextPolicy
from .models import ModelClient, ModelUsage
from .skills import SkillCatalog
from .subagents import SubagentManager
from .tasks import TaskManager
from .todo import TodoManager
from .tools import ToolContext, ToolRegistry
from .types import AssistantMessage, Message, SystemMessage, ToolCall, ToolMessage, UserMessage


@dataclass(slots=True)
class AgentResult:
    output_text: str
    messages: list[Message]
    turns: int
    stop_reason: str
    tool_results: list[Any] = field(default_factory=list)
    context_markers: list[dict[str, Any]] = field(default_factory=list)
    compact_events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class CompactResult:
    summary: str
    generation: int
    retained_turns: int
    trigger: str
    usage: ModelUsage | None = None
    message_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "generation": self.generation,
            "retained_turns": self.retained_turns,
            "trigger": self.trigger,
            "usage": None
            if self.usage is None
            else {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "message_count": self.message_count,
        }


@dataclass(slots=True)
class AgentSession:
    model: ModelClient
    tool_registry: ToolRegistry
    tool_context: ToolContext
    skill_catalog: SkillCatalog
    task_manager: TaskManager
    system_prompt: str
    max_turns: int
    messages: list[Message] = field(default_factory=list)
    active_skills: list[str] = field(default_factory=list)
    context_markers: list[ContextMarker] = field(default_factory=list)
    context_policy: ContextPolicy = field(default_factory=ContextPolicy)
    todo_manager: TodoManager = field(default_factory=TodoManager)
    rounds_since_todo: int = 0
    compact_summary: str = ""
    compact_generation: int = 0
    last_usage: ModelUsage | None = None
    auto_compact_enabled: bool = True
    compact_token_threshold: int = 6000
    compact_tail_turns: int = 2
    pending_auto_compact: bool = False
    pending_auto_compact_reason: str | None = None
    subagent_manager: SubagentManager | None = None
    background_manager: BackgroundManager | None = None

    def __post_init__(self) -> None:
        if self.subagent_manager is None:
            self.subagent_manager = SubagentManager(
                model=self.model,
                tool_registry=self.tool_registry,
                tool_context=self.tool_context,
                skill_catalog=self.skill_catalog,
                task_manager=self.task_manager,
                max_turns=min(4, self.max_turns),
            )
        if self.background_manager is None:
            self.background_manager = BackgroundManager(
                bash_policy=self.tool_context.bash_policy,
                subagent_manager=self.subagent_manager,
            )
        self._load_task_state()
        if not self.messages:
            self.messages = self._base_messages()

    async def send(self, prompt: str) -> AgentResult:
        compact_events = await self._run_pending_auto_compact()
        self.messages.append(UserMessage(content=prompt))
        result = await self._continue_loop()
        result.compact_events = compact_events
        return result

    async def plan(self, prompt: str) -> AgentResult:
        compact_events = await self._run_pending_auto_compact()
        planning_registry = ToolRegistry(tools={"todo": self.tool_registry.tools["todo"]})
        result = await self._continue_loop(
            tool_registry=planning_registry,
            nag_enabled=False,
            ephemeral_messages=[self.context_policy.planning_control_message(prompt)],
        )
        result.compact_events = compact_events
        return result

    async def load_skill(self, name: str, prompt: str | None = None) -> AgentResult:
        del prompt
        return await self._load_skill_into_context(name)

    async def invoke_skill(self, name: str, prompt: str | None = None) -> AgentResult:
        compact_events = await self._run_pending_auto_compact()
        load_result = await self._load_skill_into_context(name)
        if load_result.stop_reason != "completed":
            load_result.compact_events = compact_events
            return load_result
        result = await self._continue_loop(
            ephemeral_messages=[UserMessage(content=self._build_skill_invocation_prompt(name, prompt))]
        )
        marker = self.context_policy.skill_invocation_marker(name, prompt)
        self.context_markers.append(marker)
        result.tool_results = [*load_result.tool_results, *result.tool_results]
        result.context_markers = [marker.to_dict()]
        result.compact_events = compact_events
        return result

    async def compact(self, *, trigger: str = "manual") -> CompactResult:
        older_messages, retained_messages, retained_turns = self._split_messages_for_compact()
        summary_input = self._render_messages_for_compact(older_messages)
        next_summary = self.compact_summary
        usage: ModelUsage | None = None
        if summary_input or self.compact_summary:
            response = await self.model.complete(self._build_compact_messages(summary_input), [])
            usage = response.usage
            next_summary = response.message.content.strip() or self.compact_summary
        self.compact_summary = next_summary
        self.compact_generation += 1
        self._persist_current_task_state()
        self.messages = self._rebuild_messages(retained_messages)
        self.pending_auto_compact = False
        self.pending_auto_compact_reason = None
        return CompactResult(
            summary=self.compact_summary,
            generation=self.compact_generation,
            retained_turns=retained_turns,
            trigger=trigger,
            usage=usage,
            message_count=len(self.messages),
        )

    async def _load_skill_into_context(self, name: str) -> AgentResult:
        if name not in self.skill_catalog.records:
            return AgentResult(
                output_text="",
                messages=list(self.messages),
                turns=0,
                stop_reason="invalid-skill",
                error=f"Unknown skill: {name}",
            )
        if name in self.active_skills:
            return AgentResult(
                output_text="",
                messages=list(self.messages),
                turns=0,
                stop_reason="completed",
                tool_results=[],
            )
        tool_call = ToolCall(
            tool_name="load_skill",
            args={"name": name},
            tool_call_id=f"load-skill-{len(self.active_skills) + 1}",
        )
        self.messages.append(AssistantMessage(tool_calls=[tool_call]))
        skill_registry = ToolRegistry(tools={"load_skill": self.tool_registry.tools["load_skill"]})
        tool_results = await skill_registry.dispatch([tool_call], self._tool_context())
        self.messages.append(ToolMessage(results=tool_results))
        if any(tool_result.tool_name == "load_skill" and not tool_result.is_error for tool_result in tool_results):
            if name not in self.active_skills:
                self.active_skills.append(name)
            return AgentResult(
                output_text="",
                messages=list(self.messages),
                turns=0,
                stop_reason="completed",
                tool_results=tool_results,
            )
        error = next(
            (
                str(tool_result.content.get("error"))
                for tool_result in tool_results
                if tool_result.is_error and isinstance(tool_result.content, dict) and "error" in tool_result.content
            ),
            f"Failed to load skill: {name}",
        )
        return AgentResult(
            output_text="",
            messages=list(self.messages),
            turns=0,
            stop_reason="runtime-error",
            tool_results=tool_results,
            error=error,
        )

    def reset(self) -> None:
        self.active_skills = []
        self.context_markers = []
        self.rounds_since_todo = 0
        self.last_usage = None
        self.pending_auto_compact = False
        self.pending_auto_compact_reason = None
        self.todo_manager.reset()
        self.compact_summary = ""
        self.compact_generation = 0
        self._load_task_state()
        self.messages = self._base_messages()

    @property
    def todo_items(self) -> list[dict[str, object]]:
        return [dict(id=item.id, text=item.text, status=item.status) for item in self.todo_manager.items]

    @property
    def todo_summary(self) -> str:
        return self.todo_manager.render()

    @property
    def current_task(self) -> dict[str, Any] | None:
        task = self.task_manager.current_task
        if task is None:
            return None
        return next((item for item in self.task_manager.list_tasks() if item["id"] == task.id), None)

    @property
    def tasks(self) -> list[dict[str, Any]]:
        return self.task_manager.list_tasks()

    async def use_task(self, task_id: str) -> dict[str, Any]:
        self._persist_current_task_state()
        record = self.task_manager.use_task(task_id)
        self.context_markers = []
        self.rounds_since_todo = 0
        self._load_task_state()
        self.messages = self._base_messages()
        return next(task for task in self.task_manager.list_tasks() if task["id"] == record.id)

    async def _continue_loop(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        nag_enabled: bool = True,
        ephemeral_messages: list[Message] | None = None,
    ) -> AgentResult:
        last_text = ""
        all_tool_results: list[Any] = []
        start_assistant_count = sum(isinstance(message, AssistantMessage) for message in self.messages)
        active_registry = tool_registry or self.tool_registry
        used_todo = False
        should_schedule_auto_compact = False
        try:
            for _ in range(self.max_turns):
                request_messages = list(self.messages)
                if ephemeral_messages:
                    request_messages.extend(ephemeral_messages)
                if self.background_manager is not None:
                    notifications = self.background_manager.drain_notifications()
                    if notifications:
                        request_messages.append(self.context_policy.background_results_message(notifications))
                if nag_enabled and self.rounds_since_todo >= 3:
                    request_messages.append(self.context_policy.reminder_message())
                response = await self.model.complete(request_messages, active_registry.to_model_tools())
                self.last_usage = response.usage
                if self._should_auto_compact(response.usage):
                    should_schedule_auto_compact = True
                assistant = response.message
                self.messages.append(assistant)
                if assistant.tool_calls:
                    if any(tool_call.tool_name == "task_use" for tool_call in assistant.tool_calls):
                        self._persist_current_task_state()
                    tool_results = await active_registry.dispatch(assistant.tool_calls, self._tool_context())
                    all_tool_results.extend(tool_results)
                    persistent_results = self.context_policy.persistent_tool_results(tool_results)
                    self.messages.append(ToolMessage(results=persistent_results))
                    if any(result.tool_name == "todo" and not result.is_error for result in tool_results):
                        used_todo = True
                        self.rounds_since_todo = 0
                        self._persist_current_task_state()
                    if any(result.tool_name == "task_update" and not result.is_error for result in tool_results):
                        self._load_task_state()
                        self._refresh_state_messages()
                    if any(result.tool_name == "task_use" and not result.is_error for result in tool_results):
                        self.context_markers = []
                        self.rounds_since_todo = 0
                        self._load_task_state()
                        self._refresh_state_messages(retained_messages=self._last_turn_messages())
                    continue
                last_text = assistant.content
                if nag_enabled and not used_todo:
                    self.rounds_since_todo += 1
                if should_schedule_auto_compact:
                    self.pending_auto_compact = True
                    self.pending_auto_compact_reason = "usage-threshold"
                return AgentResult(
                    output_text=assistant.content,
                    messages=list(self.messages),
                    turns=sum(isinstance(message, AssistantMessage) for message in self.messages) - start_assistant_count,
                    stop_reason="completed",
                    tool_results=all_tool_results,
                    context_markers=[],
                )
            return AgentResult(
                output_text=last_text,
                messages=list(self.messages),
                turns=sum(isinstance(message, AssistantMessage) for message in self.messages) - start_assistant_count,
                stop_reason="max-turns",
                tool_results=all_tool_results,
                context_markers=[],
            )
        except Exception as exc:
            return AgentResult(
                output_text=last_text,
                messages=list(self.messages),
                turns=sum(isinstance(message, AssistantMessage) for message in self.messages) - start_assistant_count,
                stop_reason="runtime-error",
                tool_results=all_tool_results,
                context_markers=[],
                error=f"{type(exc).__name__}: {exc}",
            )

    def _tool_context(self) -> ToolContext:
        return replace(
            self.tool_context,
            todo_manager=self.todo_manager,
            skill_catalog=self.skill_catalog,
            task_manager=self.task_manager,
            subagent_manager=self.subagent_manager,
            background_manager=self.background_manager,
        )

    async def _run_pending_auto_compact(self) -> list[dict[str, Any]]:
        if not self.pending_auto_compact or not self.auto_compact_enabled:
            return []
        result = await self.compact(trigger=self.pending_auto_compact_reason or "auto")
        return [result.to_dict()]

    def _should_auto_compact(self, usage: ModelUsage | None) -> bool:
        if not self.auto_compact_enabled or usage is None:
            return False
        return usage.prompt_tokens >= self.compact_token_threshold or usage.total_tokens >= self.compact_token_threshold

    def _split_messages_for_compact(self) -> tuple[list[Message], list[Message], int]:
        turns = self._conversation_turns()
        if not turns:
            return [], [], 0
        if self.compact_tail_turns <= 0:
            return [message for turn in turns for message in turn], [], 0
        retained_turns = min(self.compact_tail_turns, len(turns))
        retained = [message for turn in turns[-retained_turns:] for message in turn]
        older = [message for turn in turns[:-retained_turns] for message in turn]
        return older, retained, retained_turns

    def _conversation_turns(self) -> list[list[Message]]:
        turns: list[list[Message]] = []
        current: list[Message] = []
        for message in self.messages:
            if self._is_state_message(message):
                continue
            if message.role == "user":
                if current:
                    turns.append(current)
                current = [message]
                continue
            if current:
                current.append(message)
        if current:
            turns.append(current)
        return turns

    def _is_state_message(self, message: Message) -> bool:
        if message.role == "system":
            return True
        if (
            self.context_policy.is_compact_summary_message(message)
            or self.context_policy.is_todo_state_message(message)
            or self.context_policy.is_task_state_message(message)
        ):
            return True
        if isinstance(message, AssistantMessage) and message.tool_calls:
            return all(tool_call.tool_name in {"load_skill", "todo"} for tool_call in message.tool_calls)
        if isinstance(message, ToolMessage):
            return all(result.tool_name in {"load_skill", "todo"} for result in message.results)
        return False

    def _build_compact_messages(self, transcript: str) -> list[Message]:
        active_skills = ", ".join(self.active_skills) if self.active_skills else "(none)"
        markers = "\n".join(marker.summary for marker in self.context_markers[-5:]) or "(none)"
        todo_summary = self.todo_manager.render() if self.todo_manager.items else "(empty)"
        current_task = self.task_manager.current_task
        task_summary = "(none)"
        if current_task is not None:
            task_summary = (
                f"Task id: {current_task.id}\n"
                f"Title: {current_task.title}\n"
                f"Status: {self.task_manager.effective_status(current_task.id)}\n"
                f"Summary: {current_task.summary or '(empty)'}\n"
                f"Notes: {' | '.join(current_task.notes[-5:]) if current_task.notes else '(empty)'}"
            )
        return [
            SystemMessage(
                content=(
                    "You are compacting conversation context for an agent runtime. Produce a concise reusable summary "
                    "using exactly these sections: Task, Constraints, Established Facts, Active Plan, Open Items, Recent Execution Context."
                )
            ),
            UserMessage(
                content=(
                    f"Existing compact summary:\n{self.compact_summary or '(none)'}\n\n"
                    f"Current task state:\n{task_summary}\n\n"
                    f"Active skills:\n{active_skills}\n\n"
                    f"Todo state:\n{todo_summary}\n\n"
                    f"Recent markers:\n{markers}\n\n"
                    f"Older conversation to compact:\n{transcript or '(no older conversation)'}"
                )
            ),
        ]

    def _render_messages_for_compact(self, messages: list[Message]) -> str:
        rendered: list[str] = []
        for message in messages:
            if message.role in {"system", "user"}:
                rendered.append(f"{message.role}: {getattr(message, 'content', '')}")
            elif isinstance(message, AssistantMessage):
                if message.tool_calls:
                    tool_names = ", ".join(tool_call.tool_name for tool_call in message.tool_calls)
                    rendered.append(f"assistant_tool_calls: {tool_names}")
                elif message.content:
                    rendered.append(f"assistant: {message.content}")
            elif isinstance(message, ToolMessage):
                for result in message.results:
                    rendered.append(f"tool[{result.tool_name}]: {result.content}")
        return "\n".join(rendered)

    def _rebuild_messages(self, retained_messages: list[Message]) -> list[Message]:
        rebuilt = self._base_messages()
        rebuilt.extend(retained_messages)
        return rebuilt

    def _base_messages(self) -> list[Message]:
        messages: list[Message] = [SystemMessage(content=self.system_prompt)]
        current_task = self.task_manager.current_task
        if current_task is not None:
            messages.append(
                self.context_policy.task_state_message(
                    task_id=current_task.id,
                    title=current_task.title,
                    status=self.task_manager.effective_status(current_task.id),
                    dependencies=list(current_task.dependencies),
                    blocked_by=self.task_manager.blocking_dependencies(current_task.id),
                    summary=current_task.summary,
                    notes=list(current_task.notes),
                )
            )
        if self.compact_summary:
            messages.append(self.context_policy.compact_summary_message(self.compact_summary, self.compact_generation))
        if self.todo_manager.items:
            messages.append(self.context_policy.todo_state_message(self.todo_manager.render()))
        messages.extend(self._persistent_skill_messages())
        return messages

    def _persistent_skill_messages(self) -> list[Message]:
        messages: list[Message] = []
        for index, name in enumerate(self.active_skills, start=1):
            record = self.skill_catalog.records.get(name)
            if record is None:
                continue
            tool_call = ToolCall(
                tool_name="load_skill",
                args={"name": name},
                tool_call_id=f"persistent-skill-{index}",
            )
            messages.append(AssistantMessage(tool_calls=[tool_call]))
            messages.append(
                ToolMessage(
                    results=self.context_policy.persistent_tool_results(
                        [
                            replace(
                                self._load_skill_result(name, tool_call.tool_call_id),
                                metadata={},
                            )
                        ]
                    )
                )
            )
        return messages

    def _refresh_state_messages(self, retained_messages: list[Message] | None = None) -> None:
        if retained_messages is None:
            retained_messages = [message for turn in self._conversation_turns() for message in turn]
        self.messages = self._base_messages()
        self.messages.extend(retained_messages)

    def _last_turn_messages(self) -> list[Message]:
        turns = self._conversation_turns()
        if not turns:
            return []
        return list(turns[-1])

    def _load_task_state(self) -> None:
        current_task = self.task_manager.current_task
        if current_task is None:
            self.todo_manager.reset()
            self.compact_summary = ""
            self.compact_generation = 0
            return
        self.todo_manager.update(current_task.todo_items) if current_task.todo_items else self.todo_manager.reset()
        self.compact_summary = current_task.compact_summary
        self.compact_generation = 1 if current_task.compact_summary else 0

    def _persist_current_task_state(self) -> None:
        current_task = self.task_manager.current_task
        if current_task is None:
            return
        self.task_manager.update_task(
            current_task.id,
            compact_summary=self.compact_summary,
            todo_items=self.todo_items,
        )

    def _load_skill_result(self, name: str, tool_call_id: str):
        record = self.skill_catalog.records[name]
        from .types import ToolResult

        return ToolResult(
            tool_name="load_skill",
            tool_call_id=tool_call_id,
            content={
                "name": record.name,
                "description": record.description,
                "content": self.skill_catalog.render_skill_content(name),
            },
        )

    def _build_skill_invocation_prompt(self, name: str, prompt: str | None) -> str:
        skill = self.skill_catalog.records[name]
        explicit_args = escape(prompt) if prompt else ""
        argument_hint = (
            f"  <argument_hint>{escape(skill.argument_hint)}</argument_hint>\n"
            if skill.argument_hint
            else ""
        )
        if prompt:
            execution_rule = (
                "Use explicit_args as the primary target for this invocation. Keep the current conversation context "
                "available as supporting background."
            )
        else:
            execution_rule = (
                "There are no explicit_args for this invocation. Infer the task from the current conversation context "
                "and apply the skill to that inferred task."
            )
        return (
            "<skill_invocation>\n"
            f"  <skill_name>{escape(name)}</skill_name>\n"
            "  <invocation_mode>explicit_slash_command</invocation_mode>\n"
            "  <argument_precedence>explicit_args_override_context_but_context_remains_available</argument_precedence>\n"
            f"{argument_hint}"
            f"  <explicit_args>{explicit_args}</explicit_args>\n"
            f"  <execution_rule>{escape(execution_rule)}</execution_rule>\n"
            "  <directive>Follow the loaded skill directly. Do not explain or summarize the skill unless the skill itself requires it.</directive>\n"
            "</skill_invocation>"
        )


@dataclass(slots=True)
class Agent:
    model: ModelClient
    tool_registry: ToolRegistry
    tool_context: ToolContext
    skill_catalog: SkillCatalog
    system_prompt: str
    task_manager: TaskManager | None = None
    max_turns: int = 8
    auto_compact_enabled: bool = True
    compact_token_threshold: int = 6000
    compact_tail_turns: int = 2

    async def run(
        self,
        prompt: str,
        *,
        activate_skills: list[str] | None = None,
    ) -> AgentResult:
        session = self.start_session()
        preload_tool_results: list[Any] = []
        if activate_skills:
            last_result: AgentResult | None = None
            for name in activate_skills:
                last_result = await session.load_skill(name)
                if last_result.stop_reason != "completed":
                    return last_result
                preload_tool_results.extend(last_result.tool_results)
            if not prompt.strip():
                if last_result is not None:
                    last_result.tool_results = preload_tool_results
                return last_result or AgentResult(output_text="", messages=list(session.messages), turns=0, stop_reason="completed")
        result = await session.send(prompt)
        result.tool_results = [*preload_tool_results, *result.tool_results]
        return result

    def start_session(self, activate_skills: list[str] | None = None) -> AgentSession:
        task_manager = self.task_manager or TaskManager.from_project(self.tool_context.workspace_root, create_if_missing=True)
        session = AgentSession(
            model=self.model,
            tool_registry=self.tool_registry,
            tool_context=self.tool_context,
            skill_catalog=self.skill_catalog,
            task_manager=task_manager,
            system_prompt=self._build_system_prompt(),
            max_turns=self.max_turns,
            auto_compact_enabled=self.auto_compact_enabled,
            compact_token_threshold=self.compact_token_threshold,
            compact_tail_turns=self.compact_tail_turns,
        )
        return session

    def _build_system_prompt(self) -> str:
        sections = [self.system_prompt.strip()]
        catalog = self.skill_catalog.render_catalog()
        if catalog:
            sections.append(catalog)
        return "\n\n".join(section for section in sections if section)
