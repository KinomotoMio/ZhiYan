from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_SEMANTICS_PATH = Path(__file__).resolve().parents[3] / "shared" / "fallback-semantics.json"


@lru_cache(maxsize=1)
def _load_fallback_semantics() -> dict[str, Any]:
    return json.loads(_SEMANTICS_PATH.read_text(encoding="utf-8"))


_SEMANTICS = _load_fallback_semantics()
_CANONICAL = _SEMANTICS["canonical"]
_LEGACY_ALIASES = _SEMANTICS["legacyAliases"]

CONTENT_GENERATING = _CANONICAL["contentGenerating"]
PENDING_SUPPLEMENT = _CANONICAL["pendingSupplement"]
FALLBACK_GENERATED = _CANONICAL["fallbackGenerated"]
STATUS_TITLE = _CANONICAL["statusTitle"]
STATUS_MESSAGE = _CANONICAL["statusMessage"]

_PLACEHOLDER_MATCH_MAP: dict[str, str] = {}


def _register_canonical(canonical_text: str, aliases: list[str]) -> None:
    for value in [canonical_text, *aliases]:
        _PLACEHOLDER_MATCH_MAP[value.strip().lower()] = canonical_text


_register_canonical(CONTENT_GENERATING, _LEGACY_ALIASES["contentGenerating"])
_register_canonical(PENDING_SUPPLEMENT, _LEGACY_ALIASES["pendingSupplement"])
_register_canonical(FALLBACK_GENERATED, _LEGACY_ALIASES["fallbackGenerated"])


def canonicalize_fallback_text(text: str) -> str:
    trimmed = text.strip()
    if not trimmed:
        return trimmed
    return _PLACEHOLDER_MATCH_MAP.get(trimmed.lower(), trimmed)


def is_placeholder_text(text: str) -> bool:
    trimmed = text.strip()
    if not trimmed:
        return False
    return trimmed.lower() in _PLACEHOLDER_MATCH_MAP


def get_bullet_fallback_status() -> dict[str, str]:
    return {
        "title": STATUS_TITLE,
        "message": STATUS_MESSAGE,
    }
