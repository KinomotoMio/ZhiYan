"""Session service singleton."""

from app.core.config import settings
from app.services.sessions.store import SessionStore

session_store = SessionStore(settings.db_path, settings.uploads_dir)

__all__ = ["session_store", "SessionStore"]
