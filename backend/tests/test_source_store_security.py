import asyncio
import tempfile
from pathlib import Path

import pytest

from app.services.document import source_store


def test_source_store_add_file_rejects_traversal_filename():
    probe = Path(tempfile.gettempdir()) / "source-store-evil.txt"
    if probe.exists():
        probe.unlink()

    with pytest.raises(ValueError):
        asyncio.run(source_store.add_file("../../source-store-evil.txt", b"evil"))

    assert not probe.exists()
