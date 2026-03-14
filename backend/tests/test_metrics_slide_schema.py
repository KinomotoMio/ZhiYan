import pytest
from pydantic import ValidationError

from app.models.layouts.schemas import BulletWithIconsData, MetricsSlideData, ThankYouData
from app.services.presentations.normalizer import normalize_metrics_slide_data


def test_metrics_slide_schema_requires_executive_summary_fields():
    with pytest.raises(ValidationError):
        MetricsSlideData.model_validate(
            {
                "title": "Legacy Snapshot",
                "metrics": [
                    {"value": "88%", "label": "Coverage"},
                    {"value": "11d", "label": "Lead Time"},
                ],
            }
        )


def test_metrics_slide_schema_accepts_executive_summary_shape():
    result = MetricsSlideData.model_validate(
        {
            "title": "Quarterly Snapshot",
            "conclusion": "Enterprise adoption is no longer the bottleneck.",
            "conclusionBrief": "Coverage expanded across the org, so review latency is the next constraint.",
            "metrics": [
                {"value": "92%", "label": "Adoption", "description": "active team usage"},
                {"value": "14d", "label": "Lead Time", "description": "from brief to deck"},
            ],
        }
    )

    assert result.conclusion == "Enterprise adoption is no longer the bottleneck."
    assert result.conclusionBrief == "Coverage expanded across the org, so review latency is the next constraint."
    assert len(result.metrics) == 2


def test_metrics_slide_normalizer_uses_readable_default_title():
    result = normalize_metrics_slide_data(
        {
            "metrics": [
                {"value": "92%", "label": "Adoption"},
                {"value": "14d", "label": "Lead Time"},
            ]
        }
    )

    assert result is not None
    assert result["title"] == "关键指标"


def test_thank_you_schema_keeps_readable_default_title():
    result = ThankYouData.model_validate({})

    assert result.title == "谢谢"


def test_bullet_with_icons_schema_accepts_explicit_status_fallback_shape():
    result = BulletWithIconsData.model_validate(
        {
            "title": "关键发现",
            "items": [],
            "status": {
                "title": "内容暂未就绪",
                "message": "该页正在生成或已回退，可稍后重试。",
            },
        }
    )

    assert result.items == []
    assert result.status is not None
    assert result.status.title == "内容暂未就绪"


def test_bullet_with_icons_schema_rejects_mixed_items_and_status():
    with pytest.raises(ValidationError):
        BulletWithIconsData.model_validate(
            {
                "title": "关键发现",
                "items": [
                    {"icon": {"query": "star"}, "title": "发现一", "description": "说明一"},
                    {"icon": {"query": "star"}, "title": "发现二", "description": "说明二"},
                    {"icon": {"query": "star"}, "title": "发现三", "description": "说明三"},
                ],
                "status": {
                    "title": "内容暂未就绪",
                    "message": "该页正在生成或已回退，可稍后重试。",
                },
            }
        )
