"""Skill 执行器 — subprocess 安全执行 Skill 脚本

安全措施：
- 路径白名单：仅允许执行 skills/ 目录下的脚本
- 超时限制：默认 30 秒
- JSON stdin/stdout 通信
"""

import asyncio
import json
import logging
import sys

from app.core.config import settings
from app.services.skill_runtime.registry import SkillRegistry

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT = 30  # seconds


class SkillExecutionError(Exception):
    pass


async def execute_skill(
    skill_name: str,
    script_name: str,
    input_data: dict,
    timeout: int = EXECUTION_TIMEOUT,
) -> dict:
    """执行 Skill 脚本

    Args:
        skill_name: Skill 名称（对应 skills/ 下的目录名）
        script_name: 脚本文件名（如 check.py）
        input_data: 传入的 JSON 数据（slides + parameters）
        timeout: 超时秒数

    Returns:
        脚本输出的 JSON 数据
    """
    registry = SkillRegistry()
    record = registry.get_record(skill_name)
    if record is None:
        raise SkillExecutionError(f"Skill 不存在: {skill_name}")

    scripts_dir = record.skill_dir / "scripts"
    script_path = (scripts_dir / script_name).resolve()

    allowed_roots = [
        settings.skills_dir.resolve(),
        settings.user_skills_dir.resolve(),
    ]
    if not any(str(script_path).startswith(str(root)) for root in allowed_roots):
        raise SkillExecutionError(f"脚本路径越权: {script_path}")

    if not script_path.exists():
        raise SkillExecutionError(f"脚本不存在: {script_path}")

    if not script_path.suffix == ".py":
        raise SkillExecutionError(f"仅支持 .py 脚本: {script_path.name}")

    input_json = json.dumps(input_data, ensure_ascii=False)

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(scripts_dir),
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=input_json.encode("utf-8")),
            timeout=timeout,
        )

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("Skill %s/%s failed (exit %d): %s", skill_name, script_name, process.returncode, error_msg)
            raise SkillExecutionError(f"脚本执行失败 (exit {process.returncode}): {error_msg[:500]}")

        output_text = stdout.decode("utf-8").strip()
        if not output_text:
            return {"status": "ok", "message": "脚本执行成功（无输出）"}

        return json.loads(output_text)

    except asyncio.TimeoutError:
        logger.error("Skill %s/%s timed out after %ds", skill_name, script_name, timeout)
        raise SkillExecutionError(f"脚本执行超时（{timeout}秒）")
    except json.JSONDecodeError as e:
        logger.error("Skill %s/%s invalid JSON output: %s", skill_name, script_name, e)
        raise SkillExecutionError(f"脚本输出不是有效 JSON: {e}")
