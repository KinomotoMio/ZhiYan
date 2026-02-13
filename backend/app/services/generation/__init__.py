"""Generation v2 service singletons."""

from app.core.config import settings
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner

job_store = GenerationJobStore(settings.project_root / "data" / "jobs")
event_bus = GenerationEventBus()
generation_runner = GenerationRunner(job_store, event_bus)

__all__ = [
    "job_store",
    "event_bus",
    "generation_runner",
    "GenerationJobStore",
    "GenerationEventBus",
    "GenerationRunner",
]
