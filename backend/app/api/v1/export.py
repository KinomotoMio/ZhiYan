"""导出 API — PPTX / PDF 下载"""

import logging

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.models.slide import Presentation

router = APIRouter()
logger = logging.getLogger(__name__)


class ExportRequest(BaseModel):
    presentation: Presentation


@router.post("/export/pptx")
async def export_pptx(req: ExportRequest):
    """导出为 PPTX 文件"""
    from app.services.export.pptx_exporter import export_pptx as do_export

    pptx_bytes = do_export(req.presentation)
    filename = f"{req.presentation.title[:30]}.pptx"

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/pdf")
async def export_pdf(req: ExportRequest):
    """导出为 PDF 文件"""
    from app.services.export.pdf_exporter import build_presentation_html, export_pdf as do_export

    html = build_presentation_html(req.presentation.model_dump(by_alias=True))

    try:
        pdf_bytes = await do_export(html)
    except RuntimeError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(e))

    filename = f"{req.presentation.title[:30]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
