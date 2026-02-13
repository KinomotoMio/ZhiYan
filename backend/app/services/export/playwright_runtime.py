"""Playwright 运行时保障 — Chromium 自动安装与限流重试。"""

import asyncio
import logging
import sys
import time

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 90
INSTALL_FAILURE_COOLDOWN_SECONDS = 300
MANUAL_INSTALL_COMMAND = "uv run playwright install chromium"

_install_lock = asyncio.Lock()
_last_install_failure_at: float | None = None
_last_install_failure_reason: str | None = None


def _is_missing_browser_error(exc: Exception) -> bool:
    msg = str(exc)
    return (
        "Executable doesn't exist" in msg
        or "Please run the following command to download new browsers" in msg
        or "browserType.launch: Executable doesn't exist" in msg
    )


def _format_runtime_error(reason: str) -> RuntimeError:
    return RuntimeError(
        "Playwright Chromium 自动安装失败。"
        f"{reason}。请手动执行: {MANUAL_INSTALL_COMMAND}"
    )


def _is_in_cooldown(cooldown_seconds: int) -> bool:
    if _last_install_failure_at is None:
        return False
    return (time.monotonic() - _last_install_failure_at) < cooldown_seconds


async def _install_chromium(timeout_seconds: int) -> tuple[bool, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "playwright",
        "install",
        "chromium",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return False, f"安装超时（>{timeout_seconds}s）"

    if process.returncode == 0:
        return True, ""

    message = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
    if not message:
        message = f"playwright install chromium exit={process.returncode}"
    return False, message


async def launch_chromium_with_auto_install(
    playwright,
    *,
    install_timeout_seconds: int = INSTALL_TIMEOUT_SECONDS,
    install_failure_cooldown_seconds: int = INSTALL_FAILURE_COOLDOWN_SECONDS,
):
    """启动 Chromium，缺失时自动安装一次并在失败后进入冷却窗口。"""
    global _last_install_failure_at, _last_install_failure_reason

    try:
        return await playwright.chromium.launch()
    except Exception as e:
        if not _is_missing_browser_error(e):
            raise

    async with _install_lock:
        # 双检：可能已被并发请求安装完成
        try:
            return await playwright.chromium.launch()
        except Exception as e:
            if not _is_missing_browser_error(e):
                raise

        if _is_in_cooldown(install_failure_cooldown_seconds):
            reason = _last_install_failure_reason or "最近一次自动安装失败，处于冷却期"
            logger.warning("Skip playwright auto-install during cooldown: %s", reason)
            raise _format_runtime_error(reason)

        logger.info(
            "Playwright Chromium missing, auto-install start (timeout=%ss)",
            install_timeout_seconds,
        )
        ok, reason = await _install_chromium(install_timeout_seconds)
        if not ok:
            _last_install_failure_at = time.monotonic()
            _last_install_failure_reason = reason
            logger.warning("Playwright Chromium auto-install failed: %s", reason)
            raise _format_runtime_error(reason)

        _last_install_failure_at = None
        _last_install_failure_reason = None
        logger.info("Playwright Chromium auto-install succeeded")

        try:
            return await playwright.chromium.launch()
        except Exception as e:
            raise _format_runtime_error(f"安装后启动失败: {e}") from e


def _reset_playwright_runtime_state_for_tests() -> None:
    global _last_install_failure_at, _last_install_failure_reason
    _last_install_failure_at = None
    _last_install_failure_reason = None
