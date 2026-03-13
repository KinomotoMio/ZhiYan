import pytest
from pydantic import ValidationError

from app.models.layouts.schemas import MetricsSlideData, ThankYouData
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
