from app.api.v2.generation import _build_source_hints


def test_build_source_hints_counts_material_categories():
    hints = _build_source_hints(
        [
            {"fileCategory": "image", "name": "hero.png"},
            {"fileCategory": "text", "name": "metrics.csv"},
            {"fileCategory": "docx", "name": "proposal.docx"},
            {"fileCategory": "unknown", "name": "blob.bin"},
        ]
    )

    assert hints.total_count == 4
    assert hints.image_count == 1
    assert hints.data_file_count == 1
    assert hints.document_count == 1
    assert hints.text_count == 1
    assert hints.other_count == 1
