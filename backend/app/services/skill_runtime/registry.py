"""Skill 发现 — 扫描 skills/ 目录，解析 SKILL.md frontmatter"""

import re
from pathlib import Path
from typing import Any

from app.core.config import settings


class SkillRegistry:
    def __init__(self, skills_dir: Path | None = None):
        self._skills_dir = skills_dir or settings.skills_dir

    def discover(self) -> list[dict[str, Any]]:
        """扫描 skills/ 目录，返回所有 Skill 元数据"""
        skills: list[dict[str, Any]] = []

        if not self._skills_dir.exists():
            return skills

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            metadata = self._parse_frontmatter(skill_md)
            if metadata:
                metadata["path"] = str(skill_dir)
                skills.append(metadata)

        return skills

    def load_skill(self, skill_name: str) -> str | None:
        """加载完整 SKILL.md 内容（用户触发 /command 时调用）"""
        skill_dir = self._skills_dir / skill_name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding="utf-8")
        return None

    @staticmethod
    def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
        """解析 YAML frontmatter"""
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not match:
            return None

        metadata: dict[str, Any] = {}
        for line in match.group(1).strip().split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                metadata[key.strip()] = value.strip()

        return metadata
