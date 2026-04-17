"""Unified skill catalog and metadata helpers for business-facing flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.generation.agentic.skills import SkillCatalog, SkillDiscovery, SkillRecord


def build_skill_catalog(project_root: Path | None = None) -> SkillCatalog:
    root = (project_root or settings.project_root).resolve()
    return SkillDiscovery(root).discover()


class SkillRegistry:
    def __init__(self, project_root: Path | None = None):
        self._project_root = (project_root or settings.project_root).resolve()

    def catalog(self) -> SkillCatalog:
        return build_skill_catalog(self._project_root)

    def discover(self) -> list[dict[str, Any]]:
        return [self._record_to_metadata(record) for record in self.catalog().records.values()]

    def get_skill(self, skill_name: str) -> dict[str, Any] | None:
        record = self.catalog().records.get(skill_name)
        if record is None:
            return None
        return self._record_to_metadata(record)

    def get_record(self, skill_name: str) -> SkillRecord | None:
        return self.catalog().records.get(skill_name)

    def load_skill(self, skill_name: str) -> str | None:
        record = self.get_record(skill_name)
        if record is None:
            return None
        return record.location.read_text(encoding="utf-8")

    def list_resource_files(self, skill_name: str) -> list[str]:
        record = self.get_record(skill_name)
        if record is None:
            return []
        return self._list_record_resources(record)

    def _list_record_resources(self, record: SkillRecord) -> list[str]:
        if record is None:
            return []

        resources: list[str] = []
        for folder_name in ("references", "scripts", "assets"):
            folder = record.skill_dir / folder_name
            if not folder.exists():
                continue
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    resources.append(str(path.relative_to(record.skill_dir)))
        return resources

    def _record_to_metadata(self, record: SkillRecord) -> dict[str, Any]:
        metadata = dict(record.metadata or {})
        metadata.update(
            {
                "id": record.name,
                "name": record.name,
                "description": record.description,
                "version": record.version,
                "command": record.command,
                "path": str(record.skill_dir),
                "scope": record.scope,
                "argument_hint": record.argument_hint,
                "default_for_output": record.default_for_output,
                "allowed_tools": record.allowed_tools,
                "resources": self._list_record_resources(record),
                "shadowed": [
                    {
                        "name": item.name,
                        "scope": item.scope,
                        "path": str(item.skill_dir),
                    }
                    for item in record.shadowed_records
                ],
                "shadowed_count": len(record.shadowed_records),
            }
        )
        return metadata
