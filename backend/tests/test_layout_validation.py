import json
from pathlib import Path

from app.models.layout_registry import get_layout


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_METADATA_PATH = REPO_ROOT / "shared" / "layout-metadata.json"
GENERATED_METADATA_PATH = REPO_ROOT / "frontend" / "src" / "generated" / "layout-metadata.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_generated_layout_metadata_matches_shared_taxonomy_fields():
    shared = _load_json(SHARED_METADATA_PATH)
    generated = _load_json(GENERATED_METADATA_PATH)

    assert generated["groupOrder"] == shared["groupOrder"]
    assert generated["subGroupsByGroup"] == shared["subGroupsByGroup"]
    assert generated["variantAxes"] == shared["variantAxes"]
    assert set(generated["layouts"]) == set(shared["layouts"])

    for layout_id, shared_layout in shared["layouts"].items():
        generated_layout = generated["layouts"][layout_id]
        assert generated_layout["group"] == shared_layout["group"]
        assert generated_layout["subGroup"] == shared_layout["subGroup"]
        assert generated_layout["variant"] == shared_layout["variant"]
        assert generated_layout["notes"] == shared_layout["notes"]


def test_backend_layout_registry_matches_shared_metadata_for_representative_layouts():
    shared = _load_json(SHARED_METADATA_PATH)["layouts"]

    for layout_id in (
        "bullet-with-icons",
        "image-and-description",
        "metrics-slide",
        "thank-you",
    ):
        entry = get_layout(layout_id)
        assert entry is not None

        expected = shared[layout_id]
        assert entry.group == expected["group"]
        assert entry.sub_group == expected["subGroup"]
        assert entry.variant.__dict__ == expected["variant"]
        assert entry.notes.__dict__ == expected["notes"]
        assert entry.description == expected["notes"]["purpose"]
