"""Shared provider-failure classification helpers for agentic generation."""

from __future__ import annotations

from pydantic_ai.exceptions import IncompleteToolCall, UnexpectedModelBehavior

_MALFORMED_RESPONSE_MARKERS = (
    "truncated",
    "malformed",
    "invalid json",
    "unexpected eof",
    "unterminated",
    "parse error",
)


def is_malformed_provider_response(exc: UnexpectedModelBehavior) -> bool:
    """Return True only for explicitly malformed or truncated provider outputs."""

    if isinstance(exc, IncompleteToolCall):
        return True

    haystack = " ".join(part for part in (exc.message, exc.body or "") if part).lower()
    if not haystack:
        return False
    return any(marker in haystack for marker in _MALFORMED_RESPONSE_MARKERS)
