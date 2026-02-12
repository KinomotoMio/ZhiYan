"""FastAPI 入口 — 知演后端"""

import asyncio
import logging
import time
import uuid

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


async def _periodic_cleanup(interval_hours: float = 6):
    """定期清理过期的临时上传文件"""
    from app.services.document.source_store import cleanup_old_uploads

    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            count = cleanup_old_uploads()
            if count > 0:
                logger.info("Cleaned up %d old upload directories", count)
        except Exception as e:
            logger.warning("Cleanup failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.core.config import reload_settings
    from app.services.document.source_store import cleanup_old_uploads

    reload_settings()
    count = cleanup_old_uploads()
    if count > 0:
        logger.info("Startup cleanup: removed %d old upload dirs", count)

    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="知演 ZhiYan API",
    description="AI PPT 生成智能体后端",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
    content_length = request.headers.get("content-length", "0")

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    log_msg = "[%s] %s %s → %d (%.2fs, body=%sB)"
    log_args = (
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration,
        content_length,
    )

    if duration > 5:
        logger.warning("SLOW " + log_msg, *log_args)
    else:
        logger.info(log_msg, *log_args)

    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后重试",
            "error_type": type(exc).__name__,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
