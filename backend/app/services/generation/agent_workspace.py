from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class AgentWorkspaceBundle:
    root: Path
    request_path: Path
    manifest_path: Path
    combined_sources_path: Path
    source_files: list[dict[str, Any]]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "request_path": str(self.request_path),
            "manifest_path": str(self.manifest_path),
            "combined_sources_path": str(self.combined_sources_path),
            "source_files": self.source_files,
        }


def build_agent_workspace(
    *,
    root: Path,
    request_payload: dict[str, Any],
    source_records: list[dict[str, Any]],
) -> AgentWorkspaceBundle:
    root = root.resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    sources_dir = root / "sources"
    artifacts_dir = root / "artifacts"
    sources_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    request_path = root / "request.json"
    request_path.write_text(_dump_json(request_payload), encoding="utf-8")

    combined_parts: list[str] = []
    manifest_sources: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []

    for index, record in enumerate(source_records, start=1):
        source_id = str(record.get("id") or f"source-{index}")
        parsed_content = str(record.get("parsed_content") or "").strip()
        file_name = f"{index:02d}-{source_id}-{_safe_slug(str(record.get('name') or source_id))}.md"
        relative_path = Path("sources") / file_name
        target_path = root / relative_path

        if parsed_content:
            file_text = parsed_content
        else:
            file_text = _render_missing_content_placeholder(record)

        target_path.write_text(file_text, encoding="utf-8")
        source_files.append(
            {
                "source_id": source_id,
                "path": str(target_path),
                "relative_path": str(relative_path),
            }
        )
        combined_parts.append(f"# Source: {record.get('name') or source_id}\n\n{file_text}".strip())
        manifest_sources.append(
            {
                "id": source_id,
                "name": record.get("name"),
                "type": record.get("type"),
                "fileCategory": record.get("fileCategory"),
                "status": record.get("status"),
                "size": record.get("size"),
                "storage_path": record.get("storage_path"),
                "parsed_content_available": bool(parsed_content),
                "workspace_text_path": str(relative_path),
                "previewSnippet": record.get("previewSnippet"),
                "metadata": record.get("metadata") or {},
                "error": record.get("error"),
            }
        )

    manifest_path = sources_dir / "manifest.json"
    manifest_path.write_text(
        _dump_json(
            {
                "source_count": len(manifest_sources),
                "sources": manifest_sources,
            }
        ),
        encoding="utf-8",
    )

    combined_sources_path = root / "sources" / "combined.md"
    combined_sources_path.write_text("\n\n---\n\n".join(part for part in combined_parts if part).strip(), encoding="utf-8")

    readme_path = root / "README.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Agent Workspace",
                "",
                "- Read `request.json` for the generation request.",
                "- Read `sources/manifest.json` to discover materials.",
                "- Read the individual files under `sources/` for source contents.",
                "- Save structured outputs under `artifacts/` when useful.",
            ]
        ),
        encoding="utf-8",
    )

    return AgentWorkspaceBundle(
        root=root,
        request_path=request_path,
        manifest_path=manifest_path,
        combined_sources_path=combined_sources_path,
        source_files=source_files,
    )


def _safe_slug(value: str) -> str:
    cleaned = _FILENAME_SANITIZER.sub("-", value.strip())
    collapsed = cleaned.strip("-._")
    return collapsed[:48] or "source"


def _render_missing_content_placeholder(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {record.get('name') or 'Untitled Source'}",
            "",
            "This source does not have parsed text content yet.",
            "",
            f"- type: {record.get('type') or 'unknown'}",
            f"- fileCategory: {record.get('fileCategory') or 'unknown'}",
            f"- status: {record.get('status') or 'unknown'}",
            f"- storage_path: {record.get('storage_path') or ''}",
            f"- previewSnippet: {record.get('previewSnippet') or ''}",
        ]
    ).strip()


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
