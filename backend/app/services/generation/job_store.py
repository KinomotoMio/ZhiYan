"""File-based job store for generation v2."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models.generation import GenerationEvent, GenerationJob


class GenerationJobStore:
    def __init__(self, root_dir: Path):
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _get_lock(self, job_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(job_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[job_id] = lock
            return lock

    def _job_path(self, job_id: str) -> Path:
        return self._root_dir / f"{job_id}.json"

    def _events_path(self, job_id: str) -> Path:
        return self._root_dir / f"{job_id}.events.ndjson"

    async def create_job(self, job: GenerationJob) -> None:
        lock = await self._get_lock(job.job_id)
        async with lock:
            await self._write_job_unlocked(job)
            events = self._events_path(job.job_id)
            if not events.exists():
                await asyncio.to_thread(events.write_text, "", "utf-8")

    async def save_job(self, job: GenerationJob) -> None:
        lock = await self._get_lock(job.job_id)
        async with lock:
            await self._write_job_unlocked(job)

    async def _write_job_unlocked(self, job: GenerationJob) -> None:
        path = self._job_path(job.job_id)
        tmp = path.with_suffix(".json.tmp")
        data = job.model_dump_json(indent=2, ensure_ascii=False)
        await asyncio.to_thread(tmp.write_text, data, "utf-8")
        await asyncio.to_thread(tmp.replace, path)

    async def get_job(self, job_id: str) -> GenerationJob | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        raw = await asyncio.to_thread(path.read_text, "utf-8")
        return GenerationJob.model_validate_json(raw)

    async def append_event(self, event: GenerationEvent) -> None:
        lock = await self._get_lock(event.job_id)
        async with lock:
            path = self._events_path(event.job_id)
            line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
            await asyncio.to_thread(_append_text, path, line)

    async def list_events(self, job_id: str) -> list[GenerationEvent]:
        path = self._events_path(job_id)
        if not path.exists():
            return []
        raw = await asyncio.to_thread(path.read_text, "utf-8")
        events: list[GenerationEvent] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                events.append(GenerationEvent.model_validate_json(line))
            except Exception:
                continue
        return sorted(events, key=lambda e: e.seq)



def _append_text(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
