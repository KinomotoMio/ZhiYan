from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services.generation.agentic.models import ModelClient, ModelResponse, ModelUsage
from app.services.generation.agentic.types import AssistantMessage, Message


@dataclass
class FakeModel(ModelClient):
    responses: list[AssistantMessage]
    usages: list[ModelUsage] = field(default_factory=list)
    seen_messages: list[list[Message]] = field(default_factory=list)
    seen_tools: list[list[dict[str, Any]]] = field(default_factory=list)

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        self.seen_messages.append(list(messages))
        self.seen_tools.append(list(tools))
        usage = self.usages.pop(0) if self.usages else ModelUsage()
        return ModelResponse(message=self.responses.pop(0), usage=usage)


@pytest.fixture
def skill_file_contents() -> str:
    return """---
name: example-skill
description: Use when the user asks for an example workflow.
argument-hint: Optional task selector or target identifier.
metadata:
  version: "1.0"
---

# Example Skill

Use this skill when you need an example workflow.
"""
