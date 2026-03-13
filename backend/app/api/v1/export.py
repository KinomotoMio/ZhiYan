"""Export API for PPTX and PDF downloads."""

import logging
import re
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.models.slide import Presentation

router = APIRouter()
logger = logging.getLogger(__name__)
_FILENAME_FALLBACK_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ExportRequest(BaseModel):
    presentation: Presentation


def _build_content_disposition(title: str, extension: str) -> str:
    raw_stem = (title or "presentation").strip()[:30] or "presentation"
    ascii_stem = raw_stem.encode("ascii", "ignore").decode("ascii")
    ascii_stem = _FILENAME_FALLBACK_RE.sub("_", ascii_stem).strip("._-")
    fallback = ascii_stem or "presentation"
    fallback_filename = f"{fallback}.{extension}"
    encoded_filename = quote(f"{raw_stem}.{extension}")
    return (
        f'attachment; filename="{fallback_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )


@router.post("/export/pptx")
async def export_pptx(req: ExportRequest):
    from app.services.export.pptx_exporter import export_pptx as do_export

    pptx_bytes = do_export(req.presentation)

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": _build_content_disposition(req.presentation.title, "pptx")},
    )


@router.post("/export/pdf")
async def export_pdf(req: ExportRequest):
    from app.services.export.pdf_exporter import build_presentation_html, export_pdf as do_export

    html = build_presentation_html(req.presentation.model_dump(by_alias=True))

    try:
        pdf_bytes = await do_export(html)
    except RuntimeError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _build_content_disposition(req.presentation.title, "pdf")},
    )
