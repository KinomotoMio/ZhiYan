"""POST /api/v1/generate — 演示文稿生成"""

import asyncio
import json
import logging
import time
from contextlib import suppress
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Request
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


def _get_request_id(request: Request | None) -> str:
    if request is None:
        return "unknown"
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)
    return request.headers.get("X-Request-ID", "unknown")


def _drain_task_exception(task: asyncio.Task) -> None:
    with suppress(asyncio.CancelledError, Exception):
        task.exception()


async def _run_with_hard_timeout(coro: Any, timeout: float):
    """Run coroutine with timeout without waiting for cancellation propagation."""
    task = asyncio.create_task(coro)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if task in done:
            return await task
        task.cancel()
        task.add_done_callback(_drain_task_exception)
        raise asyncio.TimeoutError()
    except asyncio.CancelledError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise


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
async def generate_presentation(req: GenerateRequest, request: Request):
    """生成演示文稿 — 调用 slide_pipeline"""
    _check_model_config()
    from app.core.config import settings
    from app.services.pipeline.graph import ParseDocumentNode, slide_pipeline

    title, state = _prepare_pipeline(req)
    request_id = _get_request_id(request)
    run_id = f"run-{uuid4().hex[:8]}"

    logger.info(
        "pipeline_start",
        extra={
            "event": "pipeline_start",
            "request_id": request_id,
            "run_id": run_id,
        },
    )

    try:
        result = await _run_with_hard_timeout(
            slide_pipeline.run(ParseDocumentNode(), state=state),
            timeout=float(settings.generate_timeout_seconds),
        )
        slides = result.output
    except asyncio.TimeoutError:
        logger.error(
            "pipeline_timeout",
            extra={
                "event": "pipeline_timeout",
                "request_id": request_id,
                "run_id": run_id,
                "error_type": "timeout",
            },
        )
        raise HTTPException(
            status_code=504,
            detail=f"PPT 生成超时（{settings.generate_timeout_seconds}秒），请减少页数或简化内容后重试",
        )
    except Exception as e:
        logger.exception(
            "pipeline_failed",
            extra={
                "event": "pipeline_failed",
                "request_id": request_id,
                "run_id": run_id,
                "error_type": type(e).__name__,
            },
        )
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
async def generate_presentation_stream(req: GenerateRequest, request: Request):
    """SSE 流式生成 — 实时推送进度事件"""
    _check_model_config()
    from app.core.config import settings
    from app.services.pipeline.graph import ParseDocumentNode, slide_pipeline

    title, state = _prepare_pipeline(req)
    request_id = _get_request_id(request)
    run_id = f"run-{uuid4().hex[:8]}"
    heartbeat = max(0.1, settings.sse_heartbeat_seconds)
    terminal_sent = False

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def progress_callback(stage: str, step: int, total_steps: int, message: str):
        # message 可能是 JSON 编码的特殊事件（outline_ready 等）
        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict) and parsed.get("type") in (
                "outline_ready", "slide_ready", "notes_ready",
            ):
                queue.put_nowait({**parsed, "run_id": run_id})
                return
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        event = {
            "type": "progress",
            "stage": stage,
            "step": step,
            "total_steps": total_steps,
            "message": message,
            "run_id": run_id,
        }
        queue.put_nowait(event)
        if settings.log_sse_debug:
            logger.debug(
                "progress_emit",
                extra={
                    "event": "progress_emit",
                    "request_id": request_id,
                    "run_id": run_id,
                    "stage": stage,
                    "step": step,
                    "total_steps": total_steps,
                },
            )

    def slide_callback(event: dict):
        queue.put_nowait({**event, "run_id": run_id})

    state.progress_callback = progress_callback
    state.slide_callback = slide_callback

    async def emit_terminal_error(message: str, error_type: str) -> None:
        nonlocal terminal_sent
        if terminal_sent:
            return
        terminal_sent = True
        await queue.put(
            {
                "type": "error",
                "message": message,
                "run_id": run_id,
                "error_type": error_type,
            }
        )
        logger.warning(
            "terminal_emit",
            extra={
                "event": "terminal_emit",
                "request_id": request_id,
                "run_id": run_id,
                "error_type": error_type,
            },
        )

    async def run_pipeline():
        nonlocal terminal_sent
        t0 = time.monotonic()
        logger.info(
            "provider_call_start",
            extra={
                "event": "provider_call_start",
                "request_id": request_id,
                "run_id": run_id,
            },
        )
        try:
            result = await _run_with_hard_timeout(
                slide_pipeline.run(ParseDocumentNode(), state=state),
                timeout=float(settings.generate_timeout_seconds),
            )
            slides = result.output
            presentation = Presentation(
                presentationId=f"pres-{uuid4().hex[:8]}",
                title=title,
                slides=slides,
            )
            terminal_sent = True
            await queue.put(
                {
                    "type": "result",
                    "presentation": json.loads(
                        presentation.model_dump_json(by_alias=True)
                    ),
                    "run_id": run_id,
                }
            )
            logger.info(
                "terminal_emit",
                extra={
                    "event": "terminal_emit",
                    "request_id": request_id,
                    "run_id": run_id,
                },
            )
            logger.info(
                "provider_call_end",
                extra={
                    "event": "provider_call_end",
                    "request_id": request_id,
                    "run_id": run_id,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )
        except asyncio.TimeoutError:
            await emit_terminal_error(
                f"生成超时（{settings.generate_timeout_seconds}秒）",
                "timeout",
            )
            logger.warning(
                "provider_call_end",
                extra={
                    "event": "provider_call_end",
                    "request_id": request_id,
                    "run_id": run_id,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                    "error_type": "timeout",
                },
            )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            cancelling = task.cancelling() if task else 0
            if cancelling > 0:
                logger.info(
                    "provider_call_end",
                    extra={
                        "event": "provider_call_end",
                        "request_id": request_id,
                        "run_id": run_id,
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                        "error_type": "cancelled_by_client",
                    },
                )
                raise
            logger.warning(
                "unexpected_cancelled_error",
                extra={
                    "event": "unexpected_cancelled_error",
                    "request_id": request_id,
                    "run_id": run_id,
                    "error_type": "CancelledError",
                },
            )
            await emit_terminal_error("生成中断，请重试", "cancelled_error")
        except Exception as e:
            logger.exception(
                "pipeline_stream_failed",
                extra={
                    "event": "pipeline_stream_failed",
                    "request_id": request_id,
                    "run_id": run_id,
                    "error_type": type(e).__name__,
                },
            )
            await emit_terminal_error(
                f"生成失败: {type(e).__name__}: {e}",
                type(e).__name__,
            )
        except BaseException as e:
            logger.exception(
                "pipeline_stream_base_exception",
                extra={
                    "event": "pipeline_stream_base_exception",
                    "request_id": request_id,
                    "run_id": run_id,
                    "error_type": type(e).__name__,
                },
            )
            await emit_terminal_error(
                f"生成失败: {type(e).__name__}",
                type(e).__name__,
            )
        finally:
            await queue.put(None)  # sentinel

    async def event_generator():
        task = asyncio.create_task(run_pipeline())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    if settings.log_sse_debug:
                        logger.debug(
                            "stream_heartbeat",
                            extra={
                                "event": "stream_heartbeat",
                                "request_id": request_id,
                                "run_id": run_id,
                            },
                        )
                    yield ": ping\n\n"
                    continue

                if event is None:
                    if not terminal_sent:
                        await emit_terminal_error(
                            "生成流结束但未返回结果",
                            "missing_terminal_event",
                        )
                        # 兜底 error 是发到 queue 的，这里立即读取并输出
                        fallback_event = await queue.get()
                        if fallback_event:
                            yield f"data: {json.dumps(fallback_event, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            logger.info(
                "stream_close",
                extra={
                    "event": "stream_close",
                    "request_id": request_id,
                    "run_id": run_id,
                    "error_type": "client_disconnect",
                },
            )
            task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            logger.info(
                "stream_close",
                extra={
                    "event": "stream_close",
                    "request_id": request_id,
                    "run_id": run_id,
                },
            )

    logger.info(
        "stream_open",
        extra={
            "event": "stream_open",
            "request_id": request_id,
            "run_id": run_id,
        },
    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
