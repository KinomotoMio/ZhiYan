"""In-memory event bus for SSE subscribers."""

from __future__ import annotations

import asyncio

from app.models.generation import GenerationEvent


class GenerationEventBus:
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue[GenerationEvent]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue[GenerationEvent]:
        queue: asyncio.Queue[GenerationEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue[GenerationEvent]) -> None:
        async with self._lock:
            subs = self._subscribers.get(job_id)
            if not subs:
                return
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(job_id, None)

    async def publish(self, event: GenerationEvent) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(event.job_id, set()))
        for queue in queues:
            queue.put_nowait(event)
