import asyncio

import pytest

from app.services.export import playwright_runtime


class _FakeChromium:
    def __init__(self):
        self.installed = False
        self.launch_calls = 0

    async def launch(self):
        self.launch_calls += 1
        if not self.installed:
            raise RuntimeError(
                "BrowserType.launch: Executable doesn't exist at /tmp/chrome-headless-shell"
            )
        return object()


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium):
        self.chromium = chromium


def test_launch_chromium_auto_install_then_success(monkeypatch):
    chromium = _FakeChromium()
    playwright = _FakePlaywright(chromium)
    playwright_runtime._reset_playwright_runtime_state_for_tests()

    install_calls = 0

    async def fake_install(timeout_seconds: int):
        nonlocal install_calls
        install_calls += 1
        assert timeout_seconds == playwright_runtime.INSTALL_TIMEOUT_SECONDS
        chromium.installed = True
        return True, ""

    monkeypatch.setattr(playwright_runtime, "_install_chromium", fake_install)

    browser = asyncio.run(
        playwright_runtime.launch_chromium_with_auto_install(playwright)
    )
    assert browser is not None
    assert install_calls == 1
    assert chromium.launch_calls >= 3


def test_launch_chromium_auto_install_failure_has_manual_hint(monkeypatch):
    chromium = _FakeChromium()
    playwright = _FakePlaywright(chromium)
    playwright_runtime._reset_playwright_runtime_state_for_tests()

    async def fake_install(timeout_seconds: int):  # noqa: ARG001
        return False, "安装超时（>90s）"

    monkeypatch.setattr(playwright_runtime, "_install_chromium", fake_install)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(playwright_runtime.launch_chromium_with_auto_install(playwright))

    assert "自动安装失败" in str(exc_info.value)
    assert playwright_runtime.MANUAL_INSTALL_COMMAND in str(exc_info.value)


def test_launch_chromium_concurrent_requests_only_install_once(monkeypatch):
    chromium = _FakeChromium()
    playwright = _FakePlaywright(chromium)
    playwright_runtime._reset_playwright_runtime_state_for_tests()

    install_calls = 0

    async def fake_install(timeout_seconds: int):  # noqa: ARG001
        nonlocal install_calls
        install_calls += 1
        await asyncio.sleep(0.05)
        chromium.installed = True
        return True, ""

    monkeypatch.setattr(playwright_runtime, "_install_chromium", fake_install)

    async def _case():
        return await asyncio.gather(
            playwright_runtime.launch_chromium_with_auto_install(playwright),
            playwright_runtime.launch_chromium_with_auto_install(playwright),
            playwright_runtime.launch_chromium_with_auto_install(playwright),
        )

    browsers = asyncio.run(_case())
    assert len(browsers) == 3
    assert all(browser is not None for browser in browsers)
    assert install_calls == 1
