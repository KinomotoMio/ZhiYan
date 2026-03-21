"""Helpers for compact, readable loading-state generation titles."""

from __future__ import annotations

import os
import re
from typing import Iterable

DEFAULT_LOADING_TITLE = "生成中..."
_MAX_LOADING_TITLE_CHARS = 18
_LEADING_PROMPT_RE = re.compile(
    r"^(?:请(?:帮我)?|帮我|麻烦|需要|想要|我要|我想|请你|请为我|为我|给我)?"
    r"(?:基于以下内容|根据以下内容|围绕以下内容|结合以下内容)?"
    r"(?:设计|准备|创建|生成|制作|输出|整理|撰写|写|做)(?:一份|一个|一套|一页|一组|一版|份|个|套)?",
    re.IGNORECASE,
)
_TRAILING_SUFFIX_RE = re.compile(
    r"(?:的)?(?:演示文稿|演示稿|幻灯片|PPTX?|pptx?|汇报稿|汇报|分享稿|分享|报告|培训材料|方案)"
    r"(?:初稿|草稿|大纲|内容)?$",
    re.IGNORECASE,
)
_PAGE_HINT_RE = re.compile(r"(?:\d+\s*(?:页|slides?|pages?)\s*)+$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _trim_source_name(name: str) -> str:
    trimmed = str(name or "").strip()
    if not trimmed:
        return ""
    stem, ext = os.path.splitext(trimmed)
    candidate = stem or trimmed
    return candidate.strip()


def _strip_prefix_and_suffix(text: str) -> str:
    candidate = text.strip().strip("\"'“”‘’[]()【】")
    candidate = _LEADING_PROMPT_RE.sub("", candidate).strip(" ：:，,。；;、")
    candidate = _TRAILING_SUFFIX_RE.sub("", candidate).strip(" ：:，,。；;、")
    candidate = _PAGE_HINT_RE.sub("", candidate).strip(" ：:，,。；;、")
    candidate = re.sub(r"的+$", "", candidate).strip(" ：:，,。；;、")
    return candidate


def compact_loading_title(text: str | None, fallback: str = DEFAULT_LOADING_TITLE) -> str:
    normalized = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
    if not normalized:
        return fallback

    first_line = next((part.strip() for part in normalized.splitlines() if part.strip()), "")
    candidate = first_line or normalized

    if "关于" in candidate:
        candidate = candidate.rsplit("关于", 1)[-1].strip()
    elif "围绕" in candidate:
        candidate = candidate.rsplit("围绕", 1)[-1].strip()
    elif "聚焦" in candidate:
        candidate = candidate.rsplit("聚焦", 1)[-1].strip()
    elif "主题" in candidate and re.search(r"主题\s*[:：是为]", candidate):
        candidate = re.split(r"主题\s*[:：是为]", candidate, maxsplit=1)[-1].strip()

    candidate = re.split(r"[。！？!?；;，,\n]", candidate, maxsplit=1)[0].strip()
    candidate = _strip_prefix_and_suffix(candidate)

    if not candidate:
        candidate = _strip_prefix_and_suffix(first_line or normalized)
    if not candidate:
        return fallback

    if len(candidate) <= _MAX_LOADING_TITLE_CHARS:
        return candidate
    return f"{candidate[:_MAX_LOADING_TITLE_CHARS].rstrip()}..."


def build_loading_title(
    *,
    topic: str | None = None,
    source_names: Iterable[str] | None = None,
    fallback: str = DEFAULT_LOADING_TITLE,
) -> str:
    topic_title = compact_loading_title(topic, fallback="")
    if topic_title:
        return topic_title

    cleaned_names = [_trim_source_name(name) for name in (source_names or [])]
    cleaned_names = [name for name in cleaned_names if name]
    if len(cleaned_names) == 1:
        return compact_loading_title(cleaned_names[0], fallback=fallback)
    if len(cleaned_names) > 1:
        return f"基于{len(cleaned_names)}个来源生成"
    return fallback
