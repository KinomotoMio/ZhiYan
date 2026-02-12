"""Templates API — 模板上传与管理"""

import logging
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

# 内存模板存储（后续可持久化）
_template_store: dict[str, dict] = {}


@router.post("/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    """上传 PPTX 模板文件，解析并存储"""
    if not file.filename or not file.filename.endswith(".pptx"):
        raise HTTPException(status_code=422, detail="仅支持 .pptx 格式")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="文件不能超过 50MB")

    from app.services.template.parser import parse_pptx_template

    template_id = f"tpl-{uuid4().hex[:8]}"
    name = file.filename.rsplit(".", 1)[0]

    try:
        config = parse_pptx_template(content, template_id, name)
    except Exception as e:
        logger.error("Template parse failed: %s", e)
        raise HTTPException(status_code=422, detail=f"模板解析失败: {e}")

    _template_store[template_id] = {
        "id": template_id,
        "name": config.name,
        "layout_count": len(config.layouts),
        "colors": {
            "primary": config.colors.primary,
            "accent": config.colors.accent,
            "background": config.colors.background,
        },
        "font_family": config.font_family,
    }

    return {
        "template_id": template_id,
        "name": config.name,
        "layouts": len(config.layouts),
    }


@router.get("/templates")
async def list_templates():
    """获取所有模板列表"""
    # 内置模板 + 用户上传模板
    builtin = [
        {
            "id": "default",
            "name": "默认模板",
            "builtin": True,
            "colors": {"primary": "#333333", "accent": "#3b82f6", "background": "#ffffff"},
        },
        {
            "id": "hust",
            "name": "华科官方",
            "builtin": True,
            "colors": {"primary": "#1e40af", "accent": "#c41e3a", "background": "#ffffff"},
        },
        {
            "id": "dark",
            "name": "暗色主题",
            "builtin": True,
            "colors": {"primary": "#a78bfa", "accent": "#7c3aed", "background": "#1e1e2e"},
        },
    ]
    uploaded = list(_template_store.values())
    return {"templates": builtin + uploaded}
