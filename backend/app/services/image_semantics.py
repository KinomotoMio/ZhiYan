from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

ImageSource = Literal["ai", "user", "existing"]

VALID_IMAGE_SOURCES = {"ai", "user", "existing"}
IMAGE_LAYOUT_IDS = frozenset({"metrics-with-image", "image-and-description"})


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def coerce_image_source(value: Any) -> ImageSource | None:
    if not isinstance(value, str):
        return None
    source = value.strip().lower()
    if source in VALID_IMAGE_SOURCES:
        return cast(ImageSource, source)
    return None


def infer_image_source(image: Mapping[str, Any]) -> ImageSource:
    explicit = coerce_image_source(image.get("source"))
    if explicit is not None:
        return explicit

    if _as_text(image.get("url")):
        return "existing"
    if "prompt" in image:
        return "ai"
    return "user"


def normalize_image_ref_payload(image: Any) -> Any:
    if not isinstance(image, dict):
        return image

    explicit = coerce_image_source(image.get("source"))
    if explicit is not None:
        return image

    normalized = dict(image)
    normalized["source"] = infer_image_source(normalized)
    return normalized


def normalize_image_content_data(layout_id: str, content_data: dict[str, Any]) -> dict[str, Any]:
    if layout_id not in IMAGE_LAYOUT_IDS:
        return content_data

    image = content_data.get("image")
    normalized_image = normalize_image_ref_payload(image)
    if normalized_image is image:
        return content_data

    normalized = dict(content_data)
    normalized["image"] = normalized_image
    return normalized
