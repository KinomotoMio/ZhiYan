"""POST /api/v1/generate — 演示文稿生成"""

import asyncio
import json
import logging
from uuid import uuid4

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.model_status import build_model_status
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


def _check_model_config():
    """检查当前模型配置是否有可用的 API Key"""
    from app.core.config import settings

    model = settings.default_model
    status = build_model_status(model, settings)
    if not status.ready:
        raise HTTPException(422, status.message)


def _prepare_pipeline(req: GenerateRequest):
    """共享的请求预处理逻辑"""
    from app.services.document.source_store import get_combined_content

    combined = req.content
    if req.source_ids:
        source_content = get_combined_content(req.source_ids)
        combined = f"{source_content}\n\n{combined}".strip() if combined else source_content

    if not combined and not req.topic:
        raise HTTPException(status_code=422, detail="请提供来源文档或主题描述")

    title = req.topic[:50] if req.topic else (combined[:50] if combined else "新演示文稿")

    from app.services.pipeline.graph import PipelineState

    state = PipelineState(
        raw_content=combined or req.topic,
        source_ids=req.source_ids,
        topic=title,
        template_id=req.template_id,
        num_pages=max(3, min(req.num_pages, 50)),
    )
    return title, state


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
    _check_model_config()
    from app.core.config import settings
    from app.services.pipeline.graph import ParseDocumentNode, slide_pipeline

    title, state = _prepare_pipeline(req)

    logger.info("Starting pipeline: topic=%s, pages=%d", title, state.num_pages)

    try:
        result = await asyncio.wait_for(
            slide_pipeline.run(ParseDocumentNode(), state=state),
            timeout=settings.generate_timeout_seconds,
        )
        slides = result.output
    except asyncio.TimeoutError:
        logger.error("Pipeline timed out after %ds", settings.generate_timeout_seconds)
        raise HTTPException(
            status_code=504,
            detail=f"PPT 生成超时（{settings.generate_timeout_seconds}秒），请减少页数或简化内容后重试",
        )
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


@router.post("/generate/stream")
async def generate_presentation_stream(req: GenerateRequest):
    """SSE 流式生成 — 实时推送进度事件"""
    _check_model_config()
    from app.core.config import settings
    from app.services.pipeline.graph import ParseDocumentNode, slide_pipeline

    title, state = _prepare_pipeline(req)

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def progress_callback(stage: str, step: int, total_steps: int, message: str):
        queue.put_nowait({
            "type": "progress",
            "stage": stage,
            "step": step,
            "total_steps": total_steps,
            "message": message,
        })

    state.progress_callback = progress_callback

    async def run_pipeline():
        try:
            result = await asyncio.wait_for(
                slide_pipeline.run(ParseDocumentNode(), state=state),
                timeout=settings.generate_timeout_seconds,
            )
            slides = result.output
            presentation = Presentation(
                presentationId=f"pres-{uuid4().hex[:8]}",
                title=title,
                slides=slides,
            )
            await queue.put({
                "type": "result",
                "presentation": json.loads(presentation.model_dump_json(by_alias=True)),
            })
        except asyncio.TimeoutError:
            await queue.put({
                "type": "error",
                "message": f"生成超时（{settings.generate_timeout_seconds}秒）",
            })
        except Exception as e:
            logger.exception("Pipeline stream failed: %s", e)
            await queue.put({
                "type": "error",
                "message": f"生成失败: {type(e).__name__}: {e}",
            })
        finally:
            await queue.put(None)  # sentinel

    async def event_generator():
        task = asyncio.create_task(run_pipeline())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            task.cancel()
            raise

    logger.info("Starting SSE pipeline: topic=%s, pages=%d", title, state.num_pages)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
