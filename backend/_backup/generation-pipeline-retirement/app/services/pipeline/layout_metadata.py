"""Shared layout metadata loader used by both pipeline helpers and catalog code."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_METADATA_PATH = Path(__file__).resolve().parents[4] / "shared" / "layout-metadata.json"


@lru_cache(maxsize=1)
def load_layout_metadata() -> dict[str, Any]:
    with _METADATA_PATH.open(encoding="utf-8") as metadata_file:
        return json.load(metadata_file)


def get_layout_metadata_entry(layout_id: str) -> dict[str, Any]:
    return dict(load_layout_metadata().get("layouts", {}).get(layout_id, {}))
