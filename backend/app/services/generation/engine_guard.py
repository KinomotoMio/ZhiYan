"""Engine guardrails (C-plan Phase 4).

This module implements a minimal circuit breaker for generation engines based on
per-job metrics (TTFS, duration, token usage, failure/fallback rates).

Design goals:
- Off by default (`settings.generation_guardrails_enabled`).
- Deterministic, auditable decisions; persisted under data/engine_guard.json.
- Automatic fallback: when breaker is open, router forces internal_v2 for primary
  or disables sampling for shadow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    from app.models.generation import now_iso

    return now_iso()


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    vals = sorted(values)
    # nearest-rank method
    idx = max(0, min(len(vals) - 1, int(0.95 * len(vals) + 0.5) - 1))
    return int(vals[idx])


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    open: bool
    reason: str
    opened_at: str | None = None


class EngineGuardStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = asyncio.Lock()

    async def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"version": 1, "engines": {}}
        raw = await asyncio.to_thread(self._path.read_text, "utf-8")
        try:
            loaded = json.loads(raw)
        except Exception:
            return {"version": 1, "engines": {}}
        if not isinstance(loaded, dict):
            return {"version": 1, "engines": {}}
        loaded.setdefault("version", 1)
        loaded.setdefault("engines", {})
        if not isinstance(loaded["engines"], dict):
            loaded["engines"] = {}
        return loaded

    async def save(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        data = json.dumps(state, ensure_ascii=False, indent=2)
        await asyncio.to_thread(tmp.write_text, data, "utf-8")
        await asyncio.to_thread(tmp.replace, self._path)

    async def record_and_evaluate(
        self,
        *,
        mode: str,
        engine_id: str,
        metrics: dict[str, Any],
    ) -> GuardDecision:
        """Record a run and potentially open/close the breaker."""
        key = _guard_key(mode, engine_id)
        async with self._lock:
            state = await self.load()
            engines = state.setdefault("engines", {})
            entry = engines.get(key)
            if not isinstance(entry, dict):
                entry = {}
                engines[key] = entry

            open_flag = bool(entry.get("open"))
            opened_at = entry.get("opened_at") if isinstance(entry.get("opened_at"), str) else None
            open_reason = entry.get("reason") if isinstance(entry.get("reason"), str) else ""
            opened_at_epoch = entry.get("opened_at_epoch")
            if not isinstance(opened_at_epoch, (int, float)):
                opened_at_epoch = None
            window = entry.get("window")
            if not isinstance(window, list):
                window = []

            window.append({"ts": _now_iso(), **metrics})
            # Keep latest N
            window_size = max(5, int(getattr(settings, "generation_guard_window_size", 50) or 50))
            if len(window) > window_size:
                window = window[-window_size:]
            entry["window"] = window

            decision = evaluate_window(
                window,
                open_flag=open_flag,
                opened_at=opened_at,
                open_reason=open_reason,
            )

            # Persist breaker state (and transitions) for audit.
            entry["open"] = decision.open
            entry["reason"] = decision.reason
            if decision.open:
                entry["opened_at"] = decision.opened_at or opened_at or _now_iso()
                entry["opened_at_epoch"] = opened_at_epoch or time.time()
            else:
                entry["opened_at"] = None
                entry["opened_at_epoch"] = None
            entry["updated_at"] = _now_iso()
            if decision.open and not open_flag:
                logger.warning(
                    "generation_guard_opened",
                    extra={
                        "event": "generation_guard_opened",
                        "mode": mode,
                        "engine_id": engine_id,
                        "reason": decision.reason,
                    },
                )
            if (not decision.open) and open_flag:
                logger.info(
                    "generation_guard_closed",
                    extra={
                        "event": "generation_guard_closed",
                        "mode": mode,
                        "engine_id": engine_id,
                        "reason": decision.reason,
                    },
                )
            await self.save(state)
            return decision

    async def get_decision(self, *, mode: str, engine_id: str) -> GuardDecision:
        key = _guard_key(mode, engine_id)
        async with self._lock:
            state = await self.load()
            engines = state.get("engines", {})
            entry = engines.get(key) if isinstance(engines, dict) else None
            if not isinstance(entry, dict):
                return GuardDecision(allowed=True, open=False, reason="no_state")

            open_flag = bool(entry.get("open"))
            opened_at = entry.get("opened_at") if isinstance(entry.get("opened_at"), str) else None
            reason = entry.get("reason") if isinstance(entry.get("reason"), str) else ""

            # Auto-close after cooldown.
            if open_flag and opened_at:
                cooldown = int(getattr(settings, "generation_guard_open_seconds", 600) or 600)
                if cooldown > 0:
                    # opened_at is ISO but we only need elapsed seconds; use monotonic with persisted epoch fallback.
                    # Store opened_at_epoch to avoid parsing; best effort if missing.
                    opened_epoch = entry.get("opened_at_epoch")
                    if isinstance(opened_epoch, (int, float)):
                        if time.time() - float(opened_epoch) >= cooldown:
                            open_flag = False
                            reason = "cooldown_elapsed"
                            entry["open"] = False
                            entry["opened_at"] = None
                            entry["opened_at_epoch"] = None
                            entry["reason"] = reason
                            entry["updated_at"] = _now_iso()
                            await self.save(state)

            return GuardDecision(
                allowed=not open_flag,
                open=open_flag,
                reason=reason or ("open" if open_flag else "closed"),
                opened_at=opened_at,
            )

    async def open_breaker(self, *, mode: str, engine_id: str, reason: str) -> None:
        key = _guard_key(mode, engine_id)
        async with self._lock:
            state = await self.load()
            engines = state.setdefault("engines", {})
            entry = engines.get(key)
            if not isinstance(entry, dict):
                entry = {}
                engines[key] = entry
            entry["open"] = True
            entry["opened_at"] = _now_iso()
            entry["opened_at_epoch"] = time.time()
            entry["reason"] = reason
            entry["updated_at"] = _now_iso()
            await self.save(state)


def _guard_key(mode: str, engine_id: str) -> str:
    m = (mode or "primary").strip().lower()
    e = (engine_id or "").strip().lower() or "unknown"
    return f"{m}:{e}"


def _is_success_status(status: str) -> bool:
    s = (status or "").strip().lower()
    return s in {"completed", "waiting_fix_review", "waiting_outline_review"}


def evaluate_window(
    window: list[dict[str, Any]],
    *,
    open_flag: bool,
    opened_at: str | None,
    open_reason: str,
) -> GuardDecision:
    if not bool(getattr(settings, "generation_guardrails_enabled", False)):
        return GuardDecision(allowed=True, open=False, reason="guardrails_disabled")

    cooldown = int(getattr(settings, "generation_guard_open_seconds", 600) or 600)
    if open_flag and opened_at and cooldown > 0:
        # keep open until cooldown elapses (auto-close handled by get_decision)
        return GuardDecision(allowed=False, open=True, reason=open_reason or "open", opened_at=opened_at)

    statuses = [str(item.get("status") or "") for item in window if isinstance(item, dict)]
    fail_count = sum(1 for s in statuses if s and not _is_success_status(s))
    total = len(statuses)
    min_samples = int(getattr(settings, "generation_guard_min_samples", 10) or 10)
    if total < max(1, min_samples):
        return GuardDecision(allowed=True, open=False, reason=f"insufficient_samples(n={total})")

    total = max(1, total)
    fail_rate = fail_count / total

    fail_rate_threshold = float(getattr(settings, "generation_guard_fail_rate_threshold", 0.2) or 0.2)
    if fail_rate_threshold > 0 and fail_rate > fail_rate_threshold:
        reason = f"fail_rate={fail_rate:.3f} > threshold={fail_rate_threshold:.3f} (n={total})"
        return GuardDecision(allowed=False, open=True, reason=reason, opened_at=_now_iso())

    def _collect_int(name: str) -> list[int]:
        values: list[int] = []
        for item in window:
            if not isinstance(item, dict):
                continue
            v = item.get(name)
            if isinstance(v, int):
                values.append(v)
            else:
                try:
                    if v is not None:
                        values.append(int(v))
                except Exception:
                    continue
        return values

    ttfs = _collect_int("ttfs_ms")
    duration = _collect_int("duration_ms")
    tokens = _collect_int("total_tokens")

    p95_ttfs = _p95(ttfs)
    p95_duration = _p95(duration)
    p95_tokens = _p95(tokens)

    ttfs_threshold = int(getattr(settings, "generation_guard_p95_ttfs_ms_threshold", 0) or 0)
    if ttfs_threshold > 0 and p95_ttfs is not None and p95_ttfs > ttfs_threshold:
        reason = f"p95_ttfs_ms={p95_ttfs} > threshold={ttfs_threshold} (n={len(ttfs)})"
        return GuardDecision(allowed=False, open=True, reason=reason, opened_at=_now_iso())

    duration_threshold = int(getattr(settings, "generation_guard_p95_duration_ms_threshold", 0) or 0)
    if duration_threshold > 0 and p95_duration is not None and p95_duration > duration_threshold:
        reason = f"p95_duration_ms={p95_duration} > threshold={duration_threshold} (n={len(duration)})"
        return GuardDecision(allowed=False, open=True, reason=reason, opened_at=_now_iso())

    token_threshold = int(getattr(settings, "generation_guard_p95_total_tokens_threshold", 0) or 0)
    if token_threshold > 0 and p95_tokens is not None and p95_tokens > token_threshold:
        reason = f"p95_total_tokens={p95_tokens} > threshold={token_threshold} (n={len(tokens)})"
        return GuardDecision(allowed=False, open=True, reason=reason, opened_at=_now_iso())

    fallback_threshold = float(getattr(settings, "generation_guard_fallback_rate_threshold", 0.0) or 0.0)
    if fallback_threshold > 0:
        fallback_rates: list[float] = []
        for item in window:
            if not isinstance(item, dict):
                continue
            v = item.get("fallback_rate")
            if isinstance(v, (int, float)):
                fallback_rates.append(float(v))
        if fallback_rates:
            vals = sorted(fallback_rates)
            idx = max(0, min(len(vals) - 1, int(0.95 * len(vals) + 0.5) - 1))
            p95_fallback = float(vals[idx])
            if p95_fallback > fallback_threshold:
                reason = f"p95_fallback_rate={p95_fallback:.3f} > threshold={fallback_threshold:.3f}"
                return GuardDecision(allowed=False, open=True, reason=reason, opened_at=_now_iso())

    return GuardDecision(allowed=True, open=False, reason="healthy")


class EngineGuard:
    """High-level helper used by router + runner."""

    def __init__(self, store: EngineGuardStore):
        self._store = store

    async def should_allow(self, *, mode: str, engine_id: str) -> GuardDecision:
        return await self._store.get_decision(mode=mode, engine_id=engine_id)

    async def record(self, *, mode: str, engine_id: str, metrics: dict[str, Any]) -> GuardDecision:
        return await self._store.record_and_evaluate(mode=mode, engine_id=engine_id, metrics=metrics)

    async def open(self, *, mode: str, engine_id: str, reason: str) -> None:
        await self._store.open_breaker(mode=mode, engine_id=engine_id, reason=reason)

    async def dump_state(self) -> dict[str, Any]:
        return await self._store.load()


def default_guard() -> EngineGuard:
    path = settings.project_root / "data" / "engine_guard.json"
    return EngineGuard(EngineGuardStore(path))


guard = default_guard()
