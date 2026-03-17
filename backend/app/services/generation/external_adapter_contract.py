"""External engine adapter contract (C-plan Phase 1).

This module defines a stable, testable contract for integrating external generators
such as Slidev or Presenton without forcing a large refactor upfront.

Phase 1 scope:
- Define request/result/error semantics (timeouts, retriable errors, stable codes)
- No production external engine implementation yet
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models.slide import Presentation


class ExternalEngineRequest(BaseModel):
    job_id: str
    topic: str = ""
    resolved_content: str = ""
    num_pages: int = 5
    template_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class ExternalEngineResult(BaseModel):
    presentation: Presentation
    # Optional artifacts (e.g. markdown, intermediate JSON, engine logs) for auditing/debugging.
    artifacts: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ExternalEngineError(Exception):
    code: str
    message: str
    retriable: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "error_message": self.message,
            "retriable": self.retriable,
        }


@runtime_checkable
class ExternalEngineAdapter(Protocol):
    """Adapter interface for an external engine."""

    engine_id: str

    async def generate(
        self,
        request: ExternalEngineRequest,
        *,
        timeout_seconds: float,
    ) -> ExternalEngineResult: ...
