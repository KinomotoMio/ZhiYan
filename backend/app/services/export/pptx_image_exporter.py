"""PPTX export fallback - render each slide as an image and embed into PPTX.

This is a "deliverable-first" path: output is less editable than the structured exporter,
but much more robust for complex slides (and matches the preview/HTML renderer closely).
"""

from __future__ import annotations

import io

from pptx import Presentation as PptxPresentation
from pptx.util import Inches

from app.models.slide import Presentation


SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)


async def export_pptx_as_images(presentation: Presentation) -> bytes:
    presentation_dict = presentation.model_dump(by_alias=True)

    from app.services.export.slide_screenshot import capture_slide_screenshots

    screenshots = await capture_slide_screenshots(presentation_dict)
    if not screenshots:
        raise RuntimeError("No slides available for fallback export")

    prs = PptxPresentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    blank = prs.slide_layouts[6]  # blank
    for ss in screenshots:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(
            io.BytesIO(ss.png_bytes),
            0,
            0,
            width=prs.slide_width,
            height=prs.slide_height,
        )

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()

