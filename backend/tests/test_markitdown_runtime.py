import importlib
import os
import sys
import types


def _reload_parser():
    sys.modules.pop("app.services.document.parser", None)
    return importlib.import_module("app.services.document.parser")


def test_parser_import_succeeds_without_path(monkeypatch):
    monkeypatch.delenv("PATH", raising=False)

    parser = _reload_parser()

    assert hasattr(parser, "normalize_markdown")
    assert "PATH" not in os.environ


def test_create_markitdown_converter_defaults_missing_path(monkeypatch):
    fake_module = types.ModuleType("markitdown")

    class FakeMarkItDown:
        pass

    fake_module.MarkItDown = FakeMarkItDown

    monkeypatch.delenv("PATH", raising=False)
    monkeypatch.delenv("Path", raising=False)
    monkeypatch.setitem(sys.modules, "markitdown", fake_module)

    parser = _reload_parser()
    converter = parser.create_markitdown_converter()

    assert isinstance(converter, FakeMarkItDown)
    assert os.environ["PATH"] == ""
