import json
from pathlib import Path

from app.models.layout_registry import get_all_layouts, get_layout


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


def test_backend_layout_registry_matches_shared_metadata():
    shared = _load_json(SHARED_METADATA_PATH)["layouts"]

    all_registered_ids = {entry.id for entry in get_all_layouts()}
    all_shared_ids = set(shared.keys())
    assert all_registered_ids == all_shared_ids

    for layout_id, expected in shared.items():
        entry = get_layout(layout_id)
        assert entry is not None
        assert entry.group == expected["group"]
        assert entry.sub_group == expected["subGroup"]
        assert entry.variant.__dict__ == expected["variant"]
        assert entry.notes.__dict__ == expected["notes"]
        assert entry.description == expected["notes"]["purpose"]
