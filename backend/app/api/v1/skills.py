"""GET /api/v1/skills — Skill 发现"""

from fastapi import APIRouter

from app.services.skill_runtime.registry import SkillRegistry

router = APIRouter()

_registry = SkillRegistry()


@router.get("/skills")
async def list_skills():
    """返回所有可用 Skills 的元数据"""
    skills = _registry.discover()
    return {"skills": skills}
