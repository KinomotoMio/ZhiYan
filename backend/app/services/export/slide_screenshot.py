"""Slide Screenshot — Playwright 逐页截图用于视觉审美评估

复用 pdf_exporter.build_presentation_html() 构建 HTML，
单浏览器实例逐页截图，返回 PNG bytes 列表。
"""

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SlideScreenshot:
    slide_id: str
    png_bytes: bytes


async def capture_slide_screenshots(
    presentation_dict: dict,
    *,
    job_id: str | None = None,
) -> list[SlideScreenshot]:
    """将每页 Slide 渲染为 PNG 截图

    Args:
        presentation_dict: {"title": str, "slides": [slide_dict, ...]}

    Returns:
        每页的 SlideScreenshot（slide_id + png_bytes）
    """
    from app.services.export.pdf_exporter import build_presentation_html

    slides = presentation_dict.get("slides", [])
    if not slides:
        return []

    t0 = time.monotonic()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright 未安装。请运行: uv add playwright && uv run playwright install chromium"
        )
    from app.services.export.playwright_runtime import launch_chromium_with_auto_install

    results: list[SlideScreenshot] = []

    async with async_playwright() as p:
        browser = await launch_chromium_with_auto_install(p)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        for slide_data in slides:
            slide_id = slide_data.get("slideId", slide_data.get("slide_id", "unknown"))

            # 构建单页 HTML
            single_slide_dict = {
                "title": presentation_dict.get("title", ""),
                "slides": [slide_data],
            }
            html = build_presentation_html(single_slide_dict)

            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(300)

            png_bytes = await page.screenshot(type="png", full_page=False)
            results.append(SlideScreenshot(slide_id=slide_id, png_bytes=png_bytes))

        await browser.close()

    logger.info(
        "slide_screenshots_done",
        extra={
            "event": "slide_screenshots_done",
            "job_id": job_id,
            "slide_count": len(results),
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        },
    )
    return results
