from __future__ import annotations

from pathlib import Path

from app.api.v2.router import api_v2_router


def test_active_backend_code_no_longer_imports_pipeline():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "app.services.pipeline" in text:
            offenders.append(str(path))
    assert offenders == []


def test_active_v2_router_excludes_retired_slidev_and_harness_routes():
    paths = {route.path for route in api_v2_router.routes}
    assert "/generation/slidev-mvp" not in paths
    assert all(not path.startswith("/harness") for path in paths)
