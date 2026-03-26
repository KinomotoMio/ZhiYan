"""Dev-only harness APIs."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.harness.slidev_mvp import run_slidev_mvp

router = APIRouter(prefix="/harness", tags=["harness-v2"])


class SlidevMvpRequest(BaseModel):
    topic: str = "Slidev MVP"
    content: str = ""
    num_pages: int = Field(default=5, ge=3, le=50)


class SlidevMvpResponse(BaseModel):
    markdown: str
    output_path: str
    outline: dict
    trace: list[dict]


@router.post("/slidev-mvp", response_model=SlidevMvpResponse)
async def create_slidev_mvp(req: SlidevMvpRequest):
    result = await run_slidev_mvp(
        topic=req.topic,
        content=req.content,
        num_pages=req.num_pages,
    )
    return SlidevMvpResponse(
        markdown=result.markdown,
        output_path=result.output_path,
        outline=result.outline,
        trace=[{"step": item.step, "detail": item.detail} for item in result.trace],
    )
