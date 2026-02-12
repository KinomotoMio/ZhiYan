"""Skills API — 发现 + 执行"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.skill_runtime.registry import SkillRegistry

router = APIRouter()
logger = logging.getLogger(__name__)

_registry = SkillRegistry()


@router.get("/skills")
async def list_skills():
    """返回所有可用 Skills 的元数据"""
    skills = _registry.discover()
    return {"skills": skills}


class SkillExecuteRequest(BaseModel):
    script: str = "check.py"
    slides: list[dict] = []
    parameters: dict = {}


@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, req: SkillExecuteRequest):
    """执行指定 Skill 的脚本"""
    from app.services.skill_runtime.executor import execute_skill as run_skill, SkillExecutionError

    # 校验 skill 存在
    skills = _registry.discover()
    if not any(s.get("name") == skill_id for s in skills):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 不存在")

    try:
        result = await run_skill(
            skill_name=skill_id,
            script_name=req.script,
            input_data={
                "slides": req.slides,
                "parameters": req.parameters,
            },
        )
        return {"status": "ok", "result": result}
    except SkillExecutionError as e:
        raise HTTPException(status_code=422, detail=str(e))
