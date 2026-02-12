"""POST /api/v1/generate — 演示文稿生成"""

import logging
from uuid import uuid4

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from app.models.slide import Presentation

router = APIRouter()
logger = logging.getLogger(__name__)


class GenerateRequest(BaseModel):
    content: str = ""
    topic: str = ""
    source_ids: list[str] = []
    template_id: str | None = None
    num_pages: int = 5


class GenerateResponse(BaseModel):
    presentation: Presentation


class ErrorResponse(BaseModel):
    detail: str
    error_type: str | None = None


@router.post(
    "/generate",
    response_model=GenerateResponse,
    responses={
        422: {"model": ErrorResponse, "description": "输入验证错误"},
        500: {"model": ErrorResponse, "description": "生成过程出错"},
    },
)
async def generate_presentation(req: GenerateRequest):
    """生成演示文稿 — 调用 slide_pipeline"""
    from app.services.pipeline.graph import (
        ParseDocumentNode,
        PipelineState,
        slide_pipeline,
    )

    # 拼接素材来源内容
    combined = req.content
    if req.source_ids:
        from app.services.document.source_store import get_combined_content

        source_content = get_combined_content(req.source_ids)
        combined = f"{source_content}\n\n{combined}".strip() if combined else source_content

    if not combined and not req.topic:
        raise HTTPException(status_code=422, detail="请提供来源文档或主题描述")

    title = req.topic[:50] if req.topic else (combined[:50] if combined else "新演示文稿")

    # 构建 pipeline 状态
    state = PipelineState(
        raw_content=combined or req.topic,
        source_ids=req.source_ids,
        topic=title,
        template_id=req.template_id,
        num_pages=max(3, min(req.num_pages, 50)),
    )

    logger.info("Starting pipeline: topic=%s, pages=%d", title, state.num_pages)

    try:
        result = await slide_pipeline.run(
            ParseDocumentNode(),
            state=state,
        )
        slides = result.output
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"PPT 生成失败: {type(e).__name__}: {e}",
        )

    presentation = Presentation(
        presentationId=f"pres-{uuid4().hex[:8]}",
        title=title,
        slides=slides,
    )
    return GenerateResponse(presentation=presentation)
