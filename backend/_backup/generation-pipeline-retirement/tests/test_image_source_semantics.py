import asyncio

from app.services.agents.slide_generator import SLIDE_GEN_INSTRUCTIONS
from app.services.pipeline.graph import PipelineState, stage_resolve_assets


def test_stage_resolve_assets_infers_existing_source_from_url():
    async def _case() -> None:
        state = PipelineState(
            slide_contents=[
                {
                    "slide_number": 1,
                    "layout_id": "metrics-with-image",
                    "content_data": {
                        "title": "Metrics",
                        "metrics": [{"value": "42", "label": "Score"}],
                        "image": {
                            "prompt": "brand cover",
                            "url": "https://example.com/image.png",
                        },
                    },
                }
            ]
        )

        await stage_resolve_assets(state)

        image = state.slides[0].content_data["image"]
        assert image["source"] == "existing"

    asyncio.run(_case())


def test_stage_resolve_assets_infers_ai_source_from_prompt_only():
    async def _case() -> None:
        state = PipelineState(
            slide_contents=[
                {
                    "slide_number": 1,
                    "layout_id": "image-and-description",
                    "content_data": {
                        "title": "AI",
                        "description": "Prompt-only image",
                        "image": {
                            "prompt": "modern office with analytics dashboard",
                        },
                    },
                }
            ]
        )

        await stage_resolve_assets(state)

        image = state.slides[0].content_data["image"]
        assert image["source"] == "ai"

    asyncio.run(_case())


def test_stage_resolve_assets_preserves_explicit_sources():
    async def _case() -> None:
        state = PipelineState(
            slide_contents=[
                {
                    "slide_number": 1,
                    "layout_id": "image-and-description",
                    "content_data": {
                        "title": "User image",
                        "description": "Needs upload",
                        "image": {
                            "source": "user",
                            "prompt": "请上传门店实拍照片",
                        },
                    },
                },
                {
                    "slide_number": 2,
                    "layout_id": "metrics-with-image",
                    "content_data": {
                        "title": "Existing asset",
                        "metrics": [{"value": "3", "label": "Assets"}],
                        "image": {
                            "source": "existing",
                            "prompt": "使用品牌图库封面图",
                            "url": None,
                        },
                    },
                },
            ]
        )

        await stage_resolve_assets(state)

        first_image = state.slides[0].content_data["image"]
        second_image = state.slides[1].content_data["image"]
        assert first_image["source"] == "user"
        assert second_image["source"] == "existing"
        assert second_image["url"] is None

    asyncio.run(_case())


def test_stage_resolve_assets_treats_empty_prompt_key_as_ai_source():
    async def _case() -> None:
        state = PipelineState(
            slide_contents=[
                {
                    "slide_number": 1,
                    "layout_id": "image-and-description",
                    "content_data": {
                        "title": "Legacy AI",
                        "description": "Empty prompt still means AI placeholder",
                        "image": {
                            "prompt": "",
                        },
                    },
                }
            ]
        )

        await stage_resolve_assets(state)

        image = state.slides[0].content_data["image"]
        assert image["source"] == "ai"

    asyncio.run(_case())


def test_slide_generator_instructions_require_image_source_semantics():
    assert "`source`" in SLIDE_GEN_INSTRUCTIONS
    assert "ai" in SLIDE_GEN_INSTRUCTIONS
    assert "user" in SLIDE_GEN_INSTRUCTIONS
    assert "existing" in SLIDE_GEN_INSTRUCTIONS
    assert "不要默认所有图片都是 AI 生成图" in SLIDE_GEN_INSTRUCTIONS
