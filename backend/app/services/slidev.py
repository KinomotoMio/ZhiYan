"""Slidev deck parse/build helpers."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings


SLIDEV_STYLE_DIR = settings.project_root / "skills" / "slidev-design-system" / "references" / "styles"
SLIDEV_LAYOUT_DIR = settings.project_root / "skills" / "slidev-design-system" / "references" / "layouts"
SLIDEV_VALIDATE_SCRIPT = settings.project_root / "skills" / "slidev-syntax" / "scripts" / "validate_deck.py"
SLIDEV_REVIEW_SCRIPT = settings.project_root / "skills" / "slidev-deck-quality" / "scripts" / "review_deck.py"
FRONTEND_DIR = settings.project_root / "frontend"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_TITLE_FRONTMATTER_RE = re.compile(r"^\s*title\s*:\s*(.+?)\s*$", re.MULTILINE)
_LAYOUT_FRONTMATTER_RE = re.compile(r"^\s*layout\s*:\s*(.+?)\s*$", re.MULTILINE)
_METADATA_ONLY_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:\s*.+$")

ROLE_TO_LAYOUT_RECIPE: dict[str, str] = {
    "cover": "cover-hero",
    "agenda": "context-brief",
    "section-divider": "context-brief",
    "narrative": "detail-focus",
    "evidence": "context-metric-stack",
    "comparison": "comparison-split",
    "process": "recommendation-actions",
    "highlight": "framework-visual",
    "closing": "closing-takeaway",
}

ROLE_TO_NATIVE_LAYOUT: dict[str, str] = {
    "cover": "cover",
    "agenda": "default",
    "section-divider": "section",
    "narrative": "default",
    "evidence": "two-cols",
    "comparison": "two-cols",
    "process": "default",
    "highlight": "default",
    "closing": "center",
}


def load_slidev_styles() -> dict[str, dict[str, Any]]:
    styles: dict[str, dict[str, Any]] = {}
    if not SLIDEV_STYLE_DIR.exists():
        return styles
    for path in sorted(SLIDEV_STYLE_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        name = str(payload.get("name") or path.stem).strip()
        if name:
            styles[name] = payload
    return styles


def load_slidev_layouts() -> dict[str, dict[str, Any]]:
    layouts: dict[str, dict[str, Any]] = {}
    if not SLIDEV_LAYOUT_DIR.exists():
        return layouts
    for path in sorted(SLIDEV_LAYOUT_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        name = str(payload.get("name") or path.stem).strip()
        if name:
            layouts[name] = payload
    return layouts


def build_slidev_role_reference_bundle(outline_items: list[dict[str, Any]]) -> dict[str, Any]:
    layouts = load_slidev_layouts()
    selected_layouts: list[dict[str, Any]] = []
    page_briefs: list[dict[str, Any]] = []
    for item in outline_items:
        slide_number = int(item.get("slide_number") or 0)
        role = str(item.get("suggested_slide_role") or "narrative").strip()
        recipe_name = ROLE_TO_LAYOUT_RECIPE.get(role, "detail-focus")
        layout_recipe = layouts.get(recipe_name, {})
        selected_layouts.append(
            {
                "slide_number": slide_number,
                "name": recipe_name,
                "preferred_layout": layout_recipe.get("preferred_layout") or ROLE_TO_NATIVE_LAYOUT.get(role, "default"),
                "description": layout_recipe.get("description") or "",
                "applies_to_roles": layout_recipe.get("applies_to_roles") or [role],
            }
        )
        page_briefs.append(
            {
                "slide_number": slide_number,
                "title": str(item.get("title") or f"第 {slide_number} 页"),
                "preferred_composition": ROLE_TO_NATIVE_LAYOUT.get(role, "default"),
                "must_keep_signals": list(layout_recipe.get("required_visual_signals") or []),
                "must_avoid_patterns": list(layout_recipe.get("forbidden_patterns") or []),
            }
        )
    return {
        "selected_layouts": selected_layouts,
        "selected_blocks": [],
        "page_briefs": page_briefs,
    }


def select_slidev_style(
    *,
    requested_style_id: str | None,
    topic: str,
    outline_items: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    styles = load_slidev_styles()
    if not styles:
        return "default", {
            "name": "default",
            "theme": "seriph",
            "description": "Fallback Slidev style.",
            "theme_config": {},
            "deck_scaffold_class": "theme-default",
            "selection_signals": [],
            "scaffold_tokens": {},
        }
    if requested_style_id and requested_style_id in styles:
        return requested_style_id, styles[requested_style_id]

    haystack_parts = [topic]
    haystack_parts.extend(str(item.get("title") or "") for item in outline_items)
    haystack_parts.extend(str(item.get("objective") or "") for item in outline_items)
    haystack = " ".join(haystack_parts).lower()

    def score(style: dict[str, Any]) -> tuple[int, str]:
        matched = sum(1 for signal in style.get("selection_signals") or [] if str(signal).lower() in haystack)
        return matched, str(style.get("name") or "")

    best = max(styles.values(), key=score)
    best_name = str(best.get("name") or "seriph")
    return best_name, best


def parse_slidev_markdown(
    *,
    markdown: str,
    outline_items: list[dict[str, Any]] | None = None,
    fallback_title: str = "新演示文稿",
    normalize_composition: bool = True,
) -> dict[str, Any]:
    text = str(markdown or "").strip()
    if not text:
        raise ValueError("Slidev markdown is empty.")
    normalized = _normalize_slidev_composition(text)[0] if normalize_composition else text
    frontmatter = _frontmatter_block(normalized)
    title = _frontmatter_title(frontmatter) or _first_heading(normalized) or fallback_title
    slides = _split_slide_chunks(normalized)
    if not slides:
        raise ValueError("Slidev markdown must contain at least one slide.")

    slide_meta: list[dict[str, Any]] = []
    outline_items = outline_items or []
    for index, chunk in enumerate(slides, start=1):
        item = outline_items[index - 1] if index - 1 < len(outline_items) else {}
        role = str(item.get("suggested_slide_role") or "narrative").strip() or "narrative"
        slide_title = (
            _slide_frontmatter_title(chunk)
            or _first_heading(chunk)
            or str(item.get("title") or f"第 {index} 页")
        )
        layout_name = _slide_layout_name(chunk) or ROLE_TO_NATIVE_LAYOUT.get(role, "default")
        slide_meta.append(
            {
                "index": index - 1,
                "slide_id": f"slide-{index}",
                "title": slide_title.strip() or f"第 {index} 页",
                "role": role,
                "layout": layout_name,
            }
        )

    return {
        "title": title,
        "slide_count": len(slide_meta),
        "slides": slide_meta,
    }


def inspect_slidev_markdown_submission(
    *,
    markdown: str,
    outline_items: list[dict[str, Any]] | None = None,
    fallback_title: str = "新演示文稿",
) -> dict[str, Any]:
    text = str(markdown or "").strip()
    if not text:
        raise ValueError("Slidev markdown is empty.")
    body = _strip_global_frontmatter(text)
    raw_chunks = _split_slide_chunks_raw(body)
    normalized_markdown, normalization = _normalize_slidev_composition(text)
    normalized_chunks = _coalesce_slide_chunks(raw_chunks)
    normalized_meta = parse_slidev_markdown(markdown=normalized_markdown, outline_items=outline_items, fallback_title=fallback_title)
    return {
        "raw_slide_count": len(raw_chunks),
        "normalized_slide_count": len(normalized_chunks),
        "normalized_markdown": normalized_markdown,
        "normalization": normalization,
        "meta": normalized_meta,
    }


def normalize_slidev_markdown(
    *,
    markdown: str,
    fallback_title: str,
    selected_style: dict[str, Any],
    paginate: bool = True,
) -> str:
    raw = str(markdown or "").strip()
    if not raw:
        raise ValueError("Slidev markdown is empty.")
    normalized_raw, _normalization = _normalize_slidev_composition(raw)
    body = _strip_global_frontmatter(normalized_raw)
    theme = str(selected_style.get("theme") or "seriph").strip() or "seriph"
    title = _frontmatter_title(_frontmatter_block(normalized_raw)) or fallback_title.strip() or "新演示文稿"
    deck_scaffold_class = str(selected_style.get("deck_scaffold_class") or "theme-default").strip()
    theme_config = selected_style.get("theme_config") if isinstance(selected_style.get("theme_config"), dict) else {}

    frontmatter_lines = [
        "---",
        f'title: "{_escape_yaml_string(title)}"',
        f'theme: "{_escape_yaml_string(theme)}"',
        "routerMode: hash",
        f"paginate: {'true' if paginate else 'false'}",
        f'class: "{_escape_yaml_string(deck_scaffold_class)}"',
    ]
    if theme_config:
        frontmatter_lines.append("themeConfig:")
        frontmatter_lines.extend(_yaml_lines(theme_config, indent=2))
    frontmatter_lines.append("---")

    scaffold = _shared_visual_scaffold(selected_style)
    normalized_body = body.strip()
    if not normalized_body:
        raise ValueError("Slidev markdown body is empty.")
    return "\n".join(frontmatter_lines) + "\n\n" + scaffold + "\n\n" + normalized_body + "\n"


async def validate_slidev_deck(
    *,
    markdown: str,
    expected_pages: int,
    selected_style: dict[str, Any],
    outline_items: list[dict[str, Any]],
) -> dict[str, Any]:
    ref_bundle = build_slidev_role_reference_bundle(outline_items)
    return await _run_script(
        SLIDEV_VALIDATE_SCRIPT,
        {
            "markdown": markdown,
            "expected_pages": expected_pages,
            "selected_style": selected_style,
            "selected_theme": {"theme": selected_style.get("theme") or "seriph"},
            "selected_layouts": ref_bundle["selected_layouts"],
            "selected_blocks": ref_bundle["selected_blocks"],
            "page_briefs": ref_bundle["page_briefs"],
            "deck_chrome": {
                "deck_scaffold_class": selected_style.get("deck_scaffold_class") or "",
            },
        },
    )


async def review_slidev_deck(
    *,
    markdown: str,
    selected_style: dict[str, Any],
    outline_items: list[dict[str, Any]],
) -> dict[str, Any]:
    ref_bundle = build_slidev_role_reference_bundle(outline_items)
    return await _run_script(
        SLIDEV_REVIEW_SCRIPT,
        {
            "markdown": markdown,
            "outline_items": outline_items,
            "selected_style": selected_style,
            "selected_theme": {"theme": selected_style.get("theme") or "seriph"},
            "selected_layouts": ref_bundle["selected_layouts"],
            "selected_blocks": ref_bundle["selected_blocks"],
            "page_briefs": ref_bundle["page_briefs"],
            "deck_chrome": {
                "deck_scaffold_class": selected_style.get("deck_scaffold_class") or "",
            },
        },
    )


async def build_slidev_spa(
    *,
    markdown: str,
    base_path: str,
    out_dir: Path,
) -> None:
    base_path = _normalize_base_path(base_path)
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="zhiyan-slidev-build-", dir=FRONTEND_DIR) as tmp_dir:
        temp_root = Path(tmp_dir)
        entry_path = temp_root / "slides.md"
        entry_path.write_text(markdown, encoding="utf-8")

        process = await asyncio.create_subprocess_exec(
            "pnpm",
            "exec",
            "slidev",
            "build",
            str(entry_path),
            "--out",
            str(out_dir),
            "--base",
            base_path,
            "--without-notes",
            cwd=str(FRONTEND_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            output = "\n".join(
                part.decode("utf-8", errors="ignore").strip()
                for part in (stdout, stderr)
                if part
            ).strip()
            raise RuntimeError(f"Slidev build failed: {output or f'exit={process.returncode}'}")
    _inject_slidev_bridge(out_dir / "index.html")


async def finalize_slidev_deck(
    *,
    markdown: str,
    fallback_title: str,
    selected_style_id: str | None,
    topic: str,
    outline_items: list[dict[str, Any]],
    expected_pages: int,
    build_base_path: str,
    build_out_dir: Path,
    paginate: bool = True,
) -> dict[str, Any]:
    prepared = await prepare_slidev_deck_artifact(
        markdown=markdown,
        fallback_title=fallback_title,
        selected_style_id=selected_style_id,
        topic=topic,
        outline_items=outline_items,
        expected_pages=expected_pages,
        paginate=paginate,
    )
    await build_slidev_spa(
        markdown=prepared["markdown"],
        base_path=build_base_path,
        out_dir=build_out_dir,
    )
    return {
        **prepared,
        "build_root": str(build_out_dir.resolve()),
        "entry_path": str((build_out_dir / "index.html").resolve()),
    }


async def prepare_slidev_deck_artifact(
    *,
    markdown: str,
    fallback_title: str,
    selected_style_id: str | None,
    topic: str,
    outline_items: list[dict[str, Any]],
    expected_pages: int,
    paginate: bool = True,
) -> dict[str, Any]:
    del topic, paginate
    raw_markdown = str(markdown or "").strip()
    if not raw_markdown:
        raise ValueError("Slidev markdown is empty.")
    meta = parse_slidev_markdown(
        markdown=raw_markdown,
        outline_items=outline_items,
        fallback_title=fallback_title,
        normalize_composition=False,
    )
    page_count_check = {
        "expected_slide_count": max(1, int(expected_pages or 1)),
        "submitted_slide_count": meta["slide_count"],
        "matches_expected": meta["slide_count"] == max(1, int(expected_pages or 1)),
        "mode": "soft",
    }
    return {
        "title": meta["title"],
        "markdown": raw_markdown + "\n",
        "meta": {
            "title": meta["title"],
            "slide_count": meta["slide_count"],
            "slides": meta["slides"],
            "selected_style_id": selected_style_id,
            "page_count_check": page_count_check,
        },
        "selected_style_id": selected_style_id,
    }


async def create_slidev_preview(
    *,
    markdown: str,
    fallback_title: str,
    selected_style_id: str | None,
    topic: str,
    outline_items: list[dict[str, Any]],
    expected_pages: int,
    preview_id: str,
) -> dict[str, Any]:
    preview_root = settings.uploads_dir / "slidev-previews" / preview_id
    build_root = preview_root / "dist"
    finalized = await finalize_slidev_deck(
        markdown=markdown,
        fallback_title=fallback_title,
        selected_style_id=selected_style_id,
        topic=topic,
        outline_items=outline_items,
        expected_pages=expected_pages,
        build_base_path=f"/api/v1/slidev-previews/{preview_id}/",
        build_out_dir=build_root,
    )
    (preview_root / "slides.md").write_text(finalized["markdown"], encoding="utf-8")
    (preview_root / "meta.json").write_text(
        json.dumps(finalized["meta"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        **finalized,
        "preview_id": preview_id,
    }


def get_slidev_preview_root(preview_id: str) -> Path:
    return (settings.uploads_dir / "slidev-previews" / preview_id).resolve()


async def _run_script(script_path: Path, parameters: dict[str, Any]) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({"parameters": parameters}, ensure_ascii=False).encode("utf-8")
    stdout, stderr = await process.communicate(payload)
    if process.returncode != 0:
        raise RuntimeError(
            f"{script_path.name} failed: {stderr.decode('utf-8', errors='ignore').strip() or process.returncode}"
        )
    raw = stdout.decode("utf-8", errors="ignore").strip()
    return json.loads(raw or "{}")


def _normalize_base_path(value: str) -> str:
    path = str(value or "/").strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"
    return path


def _inject_slidev_bridge(index_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    bridge = """
<script>
  (() => {
    const getSlideIndex = () => {
      const match = String(window.location.hash || '').match(/(\\d+)/);
      if (!match) return 0;
      const numeric = Number.parseInt(match[1], 10);
      return Number.isFinite(numeric) ? Math.max(0, numeric - 1) : 0;
    };
    const notify = () => {
      window.parent.postMessage(
        { type: 'slidev-preview-slidechange', slideIndex: getSlideIndex() },
        '*'
      );
    };
    const params = new URLSearchParams(window.location.search);
    const requested = Number.parseInt(params.get('slide') || '', 10);
    if (Number.isFinite(requested) && requested > 0 && !window.location.hash) {
      window.location.hash = '#/' + requested;
    }
    window.addEventListener('hashchange', notify);
    window.addEventListener('load', () => window.setTimeout(notify, 120));
    document.addEventListener('click', () => window.setTimeout(notify, 80), true);
  })();
</script>
""".strip()
    if "</body>" in html:
        html = html.replace("</body>", bridge + "\n</body>")
    else:
        html += "\n" + bridge + "\n"
    index_path.write_text(html, encoding="utf-8")


def _shared_visual_scaffold(selected_style: dict[str, Any]) -> str:
    deck_class = str(selected_style.get("deck_scaffold_class") or "theme-default").strip()
    tokens = selected_style.get("scaffold_tokens") if isinstance(selected_style.get("scaffold_tokens"), dict) else {}
    accent = str(tokens.get("accent") or "#171717")
    accent_soft = str(tokens.get("accent_soft") or "rgba(23,23,23,0.08)")
    surface = str(tokens.get("surface") or "rgba(255,255,255,0.92)")
    border = str(tokens.get("border") or "rgba(23,23,23,0.08)")
    text = str(tokens.get("text") or "#171717")
    muted = str(tokens.get("muted") or "#5F5F6B")
    shadow = str(tokens.get("shadow") or "0 18px 42px rgba(15,23,42,0.10)")
    return (
        '<style>\n'
        '/* slidev-shared-visual-scaffold */\n'
        f'.{deck_class} {{ --deck-accent: {accent}; --deck-accent-soft: {accent_soft}; --deck-surface: {surface}; '
        f'--deck-border: {border}; --deck-text: {text}; --deck-muted: {muted}; --deck-shadow: {shadow}; color: var(--deck-text); }}\n'
        f'.{deck_class} .insight-card, .{deck_class} .compare-side, .{deck_class} .action-step, .{deck_class} .verdict-line {{ '
        'border-radius: 20px; border: 1px solid var(--deck-border); background: var(--deck-surface); '
        'box-shadow: var(--deck-shadow); }\n'
        f'.{deck_class} .kicker, .{deck_class} .section-kicker {{ color: var(--deck-muted); letter-spacing: 0.08em; text-transform: uppercase; }}\n'
        f'.{deck_class} .accent-bar {{ width: 56px; height: 6px; border-radius: 999px; background: var(--deck-accent); }}\n'
        f'.{deck_class} .verdict-line {{ padding: 14px 18px; border-left: 6px solid var(--deck-accent); }}\n'
        f'.{deck_class} .insight-card {{ padding: 24px; }}\n'
        '</style>'
    )


def _yaml_lines(value: Any, *, indent: int) -> list[str]:
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_lines(item, indent=indent + 2))
            elif isinstance(item, list):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_lines(item, indent=indent + 2))
            elif isinstance(item, bool):
                lines.append(f"{pad}{key}: {'true' if item else 'false'}")
            elif item is None:
                lines.append(f"{pad}{key}: null")
            elif isinstance(item, (int, float)):
                lines.append(f"{pad}{key}: {item}")
            else:
                lines.append(f'{pad}{key}: "{_escape_yaml_string(str(item))}"')
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent=indent + 2))
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent=indent + 2))
            elif isinstance(item, bool):
                lines.append(f"{pad}- {'true' if item else 'false'}")
            elif item is None:
                lines.append(f"{pad}- null")
            elif isinstance(item, (int, float)):
                lines.append(f"{pad}- {item}")
            else:
                lines.append(f'{pad}- "{_escape_yaml_string(str(item))}"')
    return lines


def _escape_yaml_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _frontmatter_block(markdown: str) -> str:
    match = _FRONTMATTER_RE.match(str(markdown or ""))
    return match.group(1) if match else ""


def _frontmatter_title(frontmatter: str) -> str:
    match = _TITLE_FRONTMATTER_RE.search(frontmatter)
    if not match:
        return ""
    return str(match.group(1)).strip().strip('"').strip("'")


def _slide_layout_name(slide: str) -> str:
    frontmatter, _remainder = _extract_slide_chunk_parts(slide)
    match = _LAYOUT_FRONTMATTER_RE.search(frontmatter)
    if not match:
        return ""
    return str(match.group(1)).strip().strip('"').strip("'")


def _slide_frontmatter_title(slide: str) -> str:
    frontmatter, _remainder = _extract_slide_chunk_parts(slide)
    return _frontmatter_title(frontmatter)


def _first_heading(markdown: str) -> str:
    match = _HEADING_RE.search(str(markdown or ""))
    return str(match.group(1)).strip() if match else ""


def _strip_global_frontmatter(markdown: str) -> str:
    return _FRONTMATTER_RE.sub("", str(markdown or ""), count=1).strip()


def _split_slide_chunks(markdown: str) -> list[str]:
    text = str(markdown or "").strip()
    if not text:
        return []
    text = _strip_global_frontmatter(text)
    return _coalesce_slide_chunks(_split_slide_chunks_raw(text))


def _split_slide_chunks_raw(text: str) -> list[str]:
    slides: list[list[str]] = [[]]
    in_code_block = False
    code_fence = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            if not in_code_block:
                in_code_block = True
                code_fence = fence
            elif fence == code_fence:
                in_code_block = False
                code_fence = ""
        if not in_code_block and stripped == "---":
            slides.append([])
            continue
        slides[-1].append(raw_line)
    return ["\n".join(chunk).strip() for chunk in slides if "\n".join(chunk).strip()]


def _normalize_slidev_composition(markdown: str) -> tuple[str, dict[str, int | bool]]:
    text = str(markdown or "").strip()
    if not text:
        return "", {
            "blank_first_slide_detected": False,
            "double_separator_frontmatter_detected": False,
            "stray_metadata_repaired_count": 0,
            "empty_slide_repaired_count": 0,
        }
    frontmatter_match = _FRONTMATTER_RE.match(text)
    frontmatter_prefix = frontmatter_match.group(0).strip() if frontmatter_match else ""
    body = _strip_global_frontmatter(text)
    raw_chunks = _split_slide_chunks_raw(body)
    if not raw_chunks:
        return text, {
            "blank_first_slide_detected": False,
            "double_separator_frontmatter_detected": False,
            "stray_metadata_repaired_count": 0,
            "empty_slide_repaired_count": 0,
        }

    normalized_chunks: list[str] = []
    stray_metadata_repaired_count = 0
    empty_slide_repaired_count = 0
    double_separator_frontmatter_detected = False
    blank_first_slide_detected = False
    pending_frontmatter = ""

    for index, chunk in enumerate(raw_chunks):
        stripped = chunk.strip()
        if not stripped:
            empty_slide_repaired_count += 1
            continue
        frontmatter_payload, remainder = _extract_slide_chunk_parts(stripped)
        if frontmatter_payload and not remainder.strip():
            stray_metadata_repaired_count += 1
            double_separator_frontmatter_detected = True
            if index == 0:
                blank_first_slide_detected = True
            pending_frontmatter = _merge_metadata_payloads(pending_frontmatter, frontmatter_payload)
            continue
        merged_frontmatter = _merge_metadata_payloads(pending_frontmatter, frontmatter_payload)
        normalized_chunks.append(_render_slide_chunk(merged_frontmatter, remainder or stripped))
        pending_frontmatter = ""

    if pending_frontmatter:
        stray_metadata_repaired_count += 1

    if not normalized_chunks:
        normalized_chunks = [chunk.strip() for chunk in raw_chunks if chunk.strip()]

    assembled_parts: list[str] = []
    if frontmatter_prefix:
        assembled_parts.append(frontmatter_prefix)
    if normalized_chunks:
        assembled_parts.append("\n\n---\n\n".join(normalized_chunks).strip())
    normalized_markdown = "\n\n".join(part for part in assembled_parts if part).strip() + "\n"
    return normalized_markdown, {
        "blank_first_slide_detected": blank_first_slide_detected,
        "double_separator_frontmatter_detected": double_separator_frontmatter_detected,
        "stray_metadata_repaired_count": stray_metadata_repaired_count,
        "empty_slide_repaired_count": empty_slide_repaired_count,
    }


def _merge_frontmatter_blocks(primary_block: str, secondary_block: str) -> str:
    primary = _frontmatter_to_mapping(_frontmatter_block(primary_block))
    secondary = _frontmatter_to_mapping(_frontmatter_block(secondary_block))
    merged = {**primary, **secondary}
    lines = ["---"]
    for key, value in merged.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def _frontmatter_to_mapping(frontmatter: str) -> dict[str, str | bool | int | float | None]:
    mapping: dict[str, str | bool | int | float | None] = {}
    for raw_line in str(frontmatter or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        raw_value = value.strip()
        if not key:
            continue
        if raw_value.lower() == "true":
            mapping[key] = True
        elif raw_value.lower() == "false":
            mapping[key] = False
        elif raw_value.lower() == "null":
            mapping[key] = None
        else:
            mapping[key] = raw_value
    return mapping


def _extract_metadata_only_block(chunk: str) -> str:
    lines = [line.strip() for line in str(chunk or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if all(_METADATA_ONLY_LINE_RE.match(line) for line in lines):
        return "\n".join(lines)
    return ""


def _strip_metadata_lines(chunk: str) -> str:
    lines = [line for line in str(chunk or "").splitlines()]
    retained = [line for line in lines if not _METADATA_ONLY_LINE_RE.match(line.strip())]
    return "\n".join(retained)


def _extract_slide_chunk_parts(chunk: str) -> tuple[str, str]:
    stripped = str(chunk or "").strip()
    if not stripped:
        return "", ""
    lines = stripped.splitlines()
    metadata_lines: list[str] = []
    remainder_start: int | None = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line and not metadata_lines:
            continue
        if _METADATA_ONLY_LINE_RE.match(line):
            metadata_lines.append(line)
            continue
        if line == "---" and metadata_lines:
            remainder_start = index + 1
            break
        metadata_lines = []
        remainder_start = 0
        break
    if metadata_lines:
        if remainder_start is None:
            return "\n".join(metadata_lines), ""
        remainder = "\n".join(lines[remainder_start:]).strip()
        return "\n".join(metadata_lines), remainder
    return "", stripped


def _merge_metadata_payloads(primary: str, secondary: str) -> str:
    if primary and secondary:
        primary_block = f"---\n{primary}\n---"
        secondary_block = f"---\n{secondary}\n---"
        merged_block = _merge_frontmatter_blocks(primary_block, secondary_block)
        return _frontmatter_block(merged_block).strip()
    return secondary or primary


def _render_slide_chunk(frontmatter_payload: str, content: str) -> str:
    content = str(content or "").strip()
    if frontmatter_payload.strip():
        if content:
            return f"{frontmatter_payload.strip()}\n---\n\n{content}"
        return frontmatter_payload.strip()
    return content


def _coalesce_slide_chunks(raw_chunks: list[str]) -> list[str]:
    slides: list[str] = []
    pending_frontmatter = ""
    for chunk in raw_chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        frontmatter_payload, remainder = _extract_slide_chunk_parts(stripped)
        if frontmatter_payload and not remainder.strip():
            pending_frontmatter = _merge_metadata_payloads(pending_frontmatter, frontmatter_payload)
            continue
        merged_frontmatter = _merge_metadata_payloads(pending_frontmatter, frontmatter_payload)
        slides.append(_render_slide_chunk(merged_frontmatter, remainder or stripped))
        pending_frontmatter = ""
    if pending_frontmatter.strip():
        slides.append(_render_slide_chunk(pending_frontmatter, ""))
    return [slide.strip() for slide in slides if slide.strip()]
