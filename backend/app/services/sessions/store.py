"""SQLite 会话存储层（workspace/session/source/presentation/chat）。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

from app.services.html_deck import normalize_html_deck
from app.services.presentations import normalize_presentation_payload

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, db_path: Path, uploads_dir: Path):
        self._db_path = db_path
        self.uploads_dir = uploads_dir
        self._write_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def init(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self.uploads_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(self._init_sync)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    label TEXT,
                    owner_type TEXT,
                    owner_id TEXT,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    title_edited_by_user INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_opened_at TEXT,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_sources (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_category TEXT,
                    size INTEGER,
                    status TEXT NOT NULL,
                    preview_snippet TEXT,
                    storage_path TEXT,
                    parsed_content TEXT,
                    metadata_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_presentations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    version_no INTEGER NOT NULL,
                    is_snapshot INTEGER NOT NULL DEFAULT 0,
                    snapshot_label TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model_meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS generation_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_planning_state (
                    session_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'agentic',
                    status TEXT NOT NULL DEFAULT 'collecting_requirements',
                    brief_json TEXT NOT NULL DEFAULT '{}',
                    outline_json TEXT NOT NULL DEFAULT '{}',
                    outline_version INTEGER NOT NULL DEFAULT 0,
                    source_ids_json TEXT NOT NULL DEFAULT '[]',
                    source_digest TEXT NOT NULL DEFAULT '',
                    outline_stale INTEGER NOT NULL DEFAULT 0,
                    active_job_id TEXT,
                    agent_workspace_root TEXT,
                    agent_session_version INTEGER NOT NULL DEFAULT 0,
                    assistant_status TEXT,
                    topic_suggestions_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_workspace_updated
                ON sessions(workspace_id, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sources_session_created
                ON session_sources(session_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_chat_session_created
                ON session_chat_messages(session_id, created_at ASC);

                CREATE INDEX IF NOT EXISTS idx_presentation_session_version
                ON session_presentations(session_id, version_no DESC);

                CREATE TABLE IF NOT EXISTS workspace_sources (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_category TEXT,
                    size INTEGER,
                    status TEXT NOT NULL,
                    content_hash TEXT,
                    preview_snippet TEXT,
                    storage_path TEXT,
                    parsed_content TEXT,
                    metadata_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_wsources_workspace
                ON workspace_sources(workspace_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS session_source_links (
                    session_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, source_id),
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_id) REFERENCES workspace_sources(id) ON DELETE CASCADE
                );
                """
            )

            def _has_column(table: str, column: str) -> bool:
                rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
                return any(str(row["name"]) == column for row in rows)

            if not _has_column("workspaces", "owner_type"):
                conn.execute("ALTER TABLE workspaces ADD COLUMN owner_type TEXT")
            if not _has_column("workspaces", "owner_id"):
                conn.execute("ALTER TABLE workspaces ADD COLUMN owner_id TEXT")
            if not _has_column("sessions", "title_edited_by_user"):
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN title_edited_by_user INTEGER NOT NULL DEFAULT 0"
                )
            if not _has_column("workspace_sources", "content_hash"):
                conn.execute("ALTER TABLE workspace_sources ADD COLUMN content_hash TEXT")
            if not _has_column("session_planning_state", "mode"):
                conn.execute("ALTER TABLE session_planning_state ADD COLUMN mode TEXT NOT NULL DEFAULT 'agentic'")
            if not _has_column("session_planning_state", "source_digest"):
                conn.execute("ALTER TABLE session_planning_state ADD COLUMN source_digest TEXT NOT NULL DEFAULT ''")
            if not _has_column("session_planning_state", "agent_workspace_root"):
                conn.execute("ALTER TABLE session_planning_state ADD COLUMN agent_workspace_root TEXT")
            if not _has_column("session_planning_state", "agent_session_version"):
                conn.execute(
                    "ALTER TABLE session_planning_state ADD COLUMN agent_session_version INTEGER NOT NULL DEFAULT 0"
                )
            if not _has_column("session_planning_state", "assistant_status"):
                conn.execute("ALTER TABLE session_planning_state ADD COLUMN assistant_status TEXT")
            if not _has_column("session_planning_state", "topic_suggestions_json"):
                conn.execute(
                    "ALTER TABLE session_planning_state ADD COLUMN topic_suggestions_json TEXT NOT NULL DEFAULT '[]'"
                )

            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_owner_unique
                ON workspaces(owner_type, owner_id)
                WHERE owner_type IS NOT NULL AND owner_id IS NOT NULL
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_wsources_workspace_content_hash_ready
                ON workspace_sources(workspace_id, content_hash)
                WHERE status='ready' AND content_hash IS NOT NULL
                """
            )

            # Migrate data from session_sources -> workspace_sources + session_source_links
            has_old_data = conn.execute(
                "SELECT COUNT(*) as cnt FROM session_sources"
            ).fetchone()["cnt"]
            has_new_data = conn.execute(
                "SELECT COUNT(*) as cnt FROM workspace_sources"
            ).fetchone()["cnt"]
            if has_old_data > 0 and has_new_data == 0:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO workspace_sources(
                        id, workspace_id, source_type, name, file_category, size,
                        status, preview_snippet, storage_path, parsed_content,
                        metadata_json, error, created_at, updated_at
                    )
                    SELECT
                        ss.id, s.workspace_id, ss.source_type, ss.name, ss.file_category, ss.size,
                        ss.status, ss.preview_snippet, ss.storage_path, ss.parsed_content,
                        ss.metadata_json, ss.error, ss.created_at, ss.updated_at
                    FROM session_sources ss
                    JOIN sessions s ON s.id = ss.session_id
                    """
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_source_links(session_id, source_id, linked_at)
                    SELECT session_id, id, created_at
                    FROM session_sources
                    """
                )
                logger.info("migrated session_sources -> workspace_sources + session_source_links")

            conn.commit()

    async def ensure_workspace(self, workspace_id: str) -> None:
        await self.init()
        async with self._write_lock:
            await asyncio.to_thread(self._ensure_workspace_sync, workspace_id)

    def _ensure_workspace_sync(self, workspace_id: str) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workspaces(id, created_at, last_seen_at)
                VALUES(?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at
                """,
                (workspace_id, now, now),
            )
            conn.commit()

    async def get_workspace(self, workspace_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_workspace_sync, workspace_id)

    def _get_workspace_sync(self, workspace_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, owner_type, owner_id, created_at, last_seen_at
                FROM workspaces
                WHERE id=?
                """,
                (workspace_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "label": row["label"],
            "owner_type": row["owner_type"],
            "owner_id": row["owner_id"],
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
        }

    async def create_session(self, workspace_id: str, title: str) -> dict:
        session_id = f"sess-{uuid4().hex[:12]}"
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._create_session_sync, session_id, workspace_id, title, now
            )
        return await self.get_session(workspace_id, session_id)

    def _create_session_sync(
        self, session_id: str, workspace_id: str, title: str, now: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    id, workspace_id, title, title_edited_by_user, status, is_pinned,
                    created_at, updated_at, last_opened_at
                ) VALUES(?, ?, ?, 0, 'active', 0, ?, ?, ?)
                """,
                (session_id, workspace_id, title, now, now, now),
            )
            conn.commit()

    async def list_sessions(
        self, workspace_id: str, q: str = "", limit: int = 50, offset: int = 0
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._list_sessions_sync, workspace_id, q, limit, offset
        )

    def _list_sessions_sync(
        self, workspace_id: str, q: str, limit: int, offset: int
    ) -> list[dict]:
        where = "workspace_id = ? AND archived_at IS NULL"
        params: list[object] = [workspace_id]
        if q.strip():
            where += " AND title LIKE ?"
            params.append(f"%{q.strip()}%")
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT s.*,
                  (SELECT COUNT(*) FROM session_source_links sl WHERE sl.session_id=s.id) AS source_count,
                  (SELECT COUNT(*) FROM session_chat_messages cm WHERE cm.session_id=s.id) AS chat_count,
                  (SELECT COUNT(*) > 0 FROM session_presentations sp WHERE sp.session_id=s.id) AS has_presentation
                FROM sessions s
                WHERE {where}
                ORDER BY s.is_pinned DESC, s.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_session_summary(row) for row in rows]

    async def get_session(self, workspace_id: str, session_id: str) -> dict:
        result = await asyncio.to_thread(
            self._get_session_sync, workspace_id, session_id
        )
        if result is None:
            raise ValueError("会话不存在")
        return result

    def _get_session_sync(self, workspace_id: str, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.*,
                  (SELECT COUNT(*) FROM session_source_links sl WHERE sl.session_id=s.id) AS source_count,
                  (SELECT COUNT(*) FROM session_chat_messages cm WHERE cm.session_id=s.id) AS chat_count,
                  (SELECT COUNT(*) > 0 FROM session_presentations sp WHERE sp.session_id=s.id) AS has_presentation
                FROM sessions s
                WHERE s.id = ? AND s.workspace_id = ? AND s.archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
        if not row:
            return None
        return self._row_to_session_summary(row)

    async def touch_session(self, workspace_id: str, session_id: str) -> None:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._touch_session_sync, workspace_id, session_id, now
            )

    def _touch_session_sync(self, workspace_id: str, session_id: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET last_opened_at=?, updated_at=?
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (now, now, session_id, workspace_id),
            )
            conn.commit()

    async def update_session(
        self,
        workspace_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
        status: str | None = None,
        archived: bool | None = None,
    ) -> dict:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._update_session_sync,
                workspace_id,
                session_id,
                title,
                is_pinned,
                status,
                archived,
                now,
            )
        return await self.get_session(workspace_id, session_id)

    def _update_session_sync(
        self,
        workspace_id: str,
        session_id: str,
        title: str | None,
        is_pinned: bool | None,
        status: str | None,
        archived: bool | None,
        now: str,
    ) -> None:
        set_parts: list[str] = ["updated_at = ?"]
        params: list[object] = [now]
        if title is not None:
            set_parts.append("title = ?")
            params.append(title)
            set_parts.append("title_edited_by_user = 1")
        if is_pinned is not None:
            set_parts.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if status is not None:
            set_parts.append("status = ?")
            params.append(status)
        if archived is not None:
            set_parts.append("archived_at = ?")
            params.append(now if archived else None)
        params.extend([session_id, workspace_id])
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE sessions
                SET {", ".join(set_parts)}
                WHERE id = ? AND workspace_id = ?
                """,
                tuple(params),
            )
            conn.commit()

    async def delete_session(self, workspace_id: str, session_id: str) -> None:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._delete_session_sync, workspace_id, session_id, now
            )

    def _delete_session_sync(self, workspace_id: str, session_id: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET archived_at=?, updated_at=?
                WHERE id=? AND workspace_id=?
                """,
                (now, now, session_id, workspace_id),
            )
            conn.commit()

    async def create_source(
        self,
        *,
        session_id: str,
        source_type: str,
        name: str,
        file_category: str | None,
        size: int | None,
        status: str,
        preview_snippet: str | None,
        storage_path: str | None,
        parsed_content: str | None,
        metadata: dict | None = None,
        error: str | None = None,
        source_id: str | None = None,
    ) -> dict:
        sid = source_id or str(uuid4())
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._create_source_sync,
                sid,
                session_id,
                source_type,
                name,
                file_category,
                size,
                status,
                preview_snippet,
                storage_path,
                parsed_content,
                metadata or {},
                error,
                now,
            )
        return await self.get_source(session_id, sid)

    def _create_source_sync(
        self,
        source_id: str,
        session_id: str,
        source_type: str,
        name: str,
        file_category: str | None,
        size: int | None,
        status: str,
        preview_snippet: str | None,
        storage_path: str | None,
        parsed_content: str | None,
        metadata: dict,
        error: str | None,
        now: str,
    ) -> None:
        with self._connect() as conn:
            # Look up workspace_id from session
            row = conn.execute(
                "SELECT workspace_id FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            workspace_id = row["workspace_id"] if row else "unknown"

            # Insert into workspace_sources
            conn.execute(
                """
                INSERT INTO workspace_sources(
                    id, workspace_id, source_type, name, file_category, size, status,
                    preview_snippet, storage_path, parsed_content, metadata_json,
                    error, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    workspace_id,
                    source_type,
                    name,
                    file_category,
                    size,
                    status,
                    preview_snippet,
                    storage_path,
                    parsed_content,
                    json.dumps(metadata, ensure_ascii=False),
                    error,
                    now,
                    now,
                ),
            )
            # Create link
            conn.execute(
                """
                INSERT OR IGNORE INTO session_source_links(session_id, source_id, linked_at)
                VALUES(?, ?, ?)
                """,
                (session_id, source_id, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            conn.commit()

    async def get_source(self, session_id: str, source_id: str) -> dict:
        row = await asyncio.to_thread(self._get_source_sync, session_id, source_id)
        if row is None:
            raise ValueError("来源不存在")
        return row

    def _get_source_sync(self, session_id: str, source_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_sources WHERE id=?",
                (source_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_source_meta(row)

    async def list_sources(self, workspace_id: str, session_id: str) -> list[dict]:
        return await asyncio.to_thread(self._list_sources_sync, workspace_id, session_id)

    def _list_sources_sync(self, workspace_id: str, session_id: str) -> list[dict]:
        with self._connect() as conn:
            session_exists = conn.execute(
                """
                SELECT 1 FROM sessions
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not session_exists:
                return []
            rows = conn.execute(
                """
                SELECT ws.*
                FROM workspace_sources ws
                JOIN session_source_links sl ON sl.source_id = ws.id
                JOIN sessions s ON s.id = sl.session_id
                WHERE sl.session_id=? AND s.workspace_id=? AND ws.workspace_id=?
                ORDER BY ws.created_at DESC
                """,
                (session_id, workspace_id, workspace_id),
            ).fetchall()
        return [self._row_to_source_meta(row) for row in rows]

    async def get_source_content(
        self, workspace_id: str, session_id: str, source_id: str
    ) -> str:
        content = await asyncio.to_thread(
            self._get_source_content_sync, workspace_id, session_id, source_id
        )
        if content is None:
            raise ValueError("来源不存在")
        return content

    def _get_source_content_sync(
        self, workspace_id: str, session_id: str, source_id: str
    ) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ws.parsed_content
                FROM workspace_sources ws
                JOIN session_source_links sl ON sl.source_id = ws.id
                JOIN sessions s ON s.id = sl.session_id
                WHERE ws.id=? AND sl.session_id=? AND s.workspace_id=? AND ws.workspace_id=?
                  AND s.archived_at IS NULL
                """,
                (source_id, session_id, workspace_id, workspace_id),
            ).fetchone()
        return None if row is None else (row["parsed_content"] or "")

    async def delete_source(
        self, workspace_id: str, session_id: str, source_id: str
    ) -> bool:
        """Unlink a source from a session (does not delete the workspace source)."""
        async with self._write_lock:
            return await asyncio.to_thread(
                self._delete_source_sync, workspace_id, session_id, source_id
            )

    def _delete_source_sync(self, workspace_id: str, session_id: str, source_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM session_source_links sl
                JOIN sessions s ON s.id=sl.session_id
                WHERE sl.source_id=? AND sl.session_id=? AND s.workspace_id=? AND s.archived_at IS NULL
                """,
                (source_id, session_id, workspace_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "DELETE FROM session_source_links WHERE source_id=? AND session_id=?",
                (source_id, session_id),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (_now_iso(), session_id),
            )
            conn.commit()
        return True

    async def get_combined_source_content(
        self, workspace_id: str, session_id: str, source_ids: list[str]
    ) -> str:
        return await asyncio.to_thread(
            self._get_combined_source_content_sync, workspace_id, source_ids
        )

    async def get_workspace_sources_by_ids(
        self, workspace_id: str, source_ids: list[str]
    ) -> list[dict]:
        """Fetch source metas for a list of ids in one query (missing ids are ignored)."""

        return await asyncio.to_thread(
            self._get_workspace_sources_by_ids_sync, workspace_id, source_ids
        )

    async def get_workspace_source_records_by_ids(
        self, workspace_id: str, source_ids: list[str]
    ) -> list[dict]:
        """Fetch richer source records for internal generation/runtime workspace use."""

        return await asyncio.to_thread(
            self._get_workspace_source_records_by_ids_sync, workspace_id, source_ids
        )

    def _get_combined_source_content_sync(
        self, workspace_id: str, source_ids: list[str]
    ) -> str:
        if not source_ids:
            return ""
        placeholders = ",".join("?" for _ in source_ids)
        params: list[object] = [workspace_id, *source_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ws.id, ws.parsed_content
                FROM workspace_sources ws
                WHERE ws.workspace_id=? AND ws.id IN ({placeholders})
                """,
                tuple(params),
            ).fetchall()
        row_map = {row["id"]: (row["parsed_content"] or "") for row in rows}
        parts = [row_map[sid] for sid in source_ids if row_map.get(sid)]
        return "\n\n---\n\n".join(parts)

    def _get_workspace_sources_by_ids_sync(
        self, workspace_id: str, source_ids: list[str]
    ) -> list[dict]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        params: list[object] = [workspace_id, *source_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ws.*
                FROM workspace_sources ws
                WHERE ws.workspace_id=? AND ws.id IN ({placeholders})
                """,
                tuple(params),
            ).fetchall()
        metas = [self._row_to_source_meta(row) for row in rows]
        meta_by_id = {meta["id"]: meta for meta in metas if isinstance(meta, dict) and meta.get("id")}
        # Preserve caller-provided ordering for deterministic counts/prompt text.
        ordered = [meta_by_id[sid] for sid in source_ids if sid in meta_by_id]
        return ordered

    def _get_workspace_source_records_by_ids_sync(
        self, workspace_id: str, source_ids: list[str]
    ) -> list[dict]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        params: list[object] = [workspace_id, *source_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ws.*
                FROM workspace_sources ws
                WHERE ws.workspace_id=? AND ws.id IN ({placeholders})
                """,
                tuple(params),
            ).fetchall()
        records_by_id: dict[str, dict] = {}
        for row in rows:
            records_by_id[str(row["id"])] = {
                "id": row["id"],
                "name": row["name"],
                "type": row["source_type"],
                "fileCategory": row["file_category"],
                "size": row["size"],
                "status": row["status"],
                "previewSnippet": row["preview_snippet"],
                "storage_path": row["storage_path"],
                "parsed_content": row["parsed_content"] or "",
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "error": row["error"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return [records_by_id[sid] for sid in source_ids if sid in records_by_id]

    # ---- Workspace-level source methods ----

    async def create_workspace_source(
        self,
        *,
        workspace_id: str,
        source_type: str,
        name: str,
        file_category: str | None,
        size: int | None,
        status: str,
        content_hash: str | None,
        preview_snippet: str | None,
        storage_path: str | None,
        parsed_content: str | None,
        metadata: dict | None = None,
        error: str | None = None,
        source_id: str | None = None,
    ) -> dict:
        sid = source_id or str(uuid4())
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._create_workspace_source_sync,
                sid, workspace_id, source_type, name, file_category, size,
                status, content_hash, preview_snippet, storage_path, parsed_content,
                metadata or {}, error, now,
            )
        return await self.get_workspace_source(workspace_id, sid)

    def _create_workspace_source_sync(
        self,
        source_id: str,
        workspace_id: str,
        source_type: str,
        name: str,
        file_category: str | None,
        size: int | None,
        status: str,
        content_hash: str | None,
        preview_snippet: str | None,
        storage_path: str | None,
        parsed_content: str | None,
        metadata: dict,
        error: str | None,
        now: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workspace_sources(
                    id, workspace_id, source_type, name, file_category, size, status,
                    content_hash, preview_snippet, storage_path, parsed_content, metadata_json,
                    error, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id, workspace_id, source_type, name, file_category, size,
                    status, content_hash, preview_snippet, storage_path, parsed_content,
                    json.dumps(metadata, ensure_ascii=False), error, now, now,
                ),
            )
            conn.commit()

    async def get_workspace_source(self, workspace_id: str, source_id: str) -> dict:
        row = await asyncio.to_thread(
            self._get_workspace_source_sync, workspace_id, source_id
        )
        if row is None:
            raise ValueError("来源不存在")
        return row

    def _get_workspace_source_sync(self, workspace_id: str, source_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_sources WHERE id=? AND workspace_id=?",
                (source_id, workspace_id),
            ).fetchone()
        if not row:
            return None
        return self._row_to_source_meta(row)

    async def get_workspace_source_content(self, workspace_id: str, source_id: str) -> str:
        content = await asyncio.to_thread(
            self._get_workspace_source_content_sync, workspace_id, source_id
        )
        if content is None:
            raise ValueError("来源不存在")
        return content

    def _get_workspace_source_content_sync(self, workspace_id: str, source_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT parsed_content FROM workspace_sources WHERE id=? AND workspace_id=?",
                (source_id, workspace_id),
            ).fetchone()
        return None if row is None else (row["parsed_content"] or "")

    async def get_workspace_source_by_hash(
        self,
        workspace_id: str,
        content_hash: str,
    ) -> dict | None:
        return await asyncio.to_thread(
            self._get_workspace_source_by_hash_sync, workspace_id, content_hash
        )

    def _get_workspace_source_by_hash_sync(
        self,
        workspace_id: str,
        content_hash: str,
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ws.*,
                       (
                         SELECT COUNT(*)
                         FROM session_source_links sl
                         JOIN sessions s ON s.id = sl.session_id
                         WHERE sl.source_id = ws.id
                           AND s.workspace_id = ws.workspace_id
                           AND s.archived_at IS NULL
                       ) AS linked_session_count
                FROM workspace_sources ws
                WHERE ws.workspace_id=? AND ws.content_hash=? AND ws.status='ready'
                LIMIT 1
                """,
                (workspace_id, content_hash),
            ).fetchone()
        return None if row is None else self._row_to_source_meta(row)

    async def list_workspace_sources(
        self,
        workspace_id: str,
        q: str = "",
        source_type: str | None = None,
        status: str | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._list_workspace_sources_sync,
            workspace_id,
            q,
            source_type,
            status,
            sort,
            limit,
            offset,
        )

    def _list_workspace_sources_sync(
        self,
        workspace_id: str,
        q: str,
        source_type: str | None,
        status: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> list[dict]:
        where = "ws.workspace_id = ?"
        params: list[object] = [workspace_id]
        if q.strip():
            where += " AND ws.name LIKE ?"
            params.append(f"%{q.strip()}%")
        if source_type:
            where += " AND ws.source_type = ?"
            params.append(source_type)
        if status:
            where += " AND ws.status = ?"
            params.append(status)

        order_by_map = {
            "created_desc": "ws.created_at DESC",
            "created_asc": "ws.created_at ASC",
            "name_asc": "ws.name COLLATE NOCASE ASC",
            "name_desc": "ws.name COLLATE NOCASE DESC",
            "linked_desc": "linked_session_count DESC, ws.created_at DESC",
        }
        order_by = order_by_map.get(sort, order_by_map["created_desc"])

        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ws.*,
                    (
                      SELECT COUNT(*)
                      FROM session_source_links sl
                      JOIN sessions s ON s.id = sl.session_id
                      WHERE sl.source_id = ws.id
                        AND s.workspace_id = ws.workspace_id
                        AND s.archived_at IS NULL
                    ) AS linked_session_count
                FROM workspace_sources ws
                WHERE {where}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_source_meta(row) for row in rows]

    async def delete_workspace_source(self, workspace_id: str, source_id: str) -> bool:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._delete_workspace_source_sync, workspace_id, source_id
            )

    def _delete_workspace_source_sync(self, workspace_id: str, source_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT storage_path FROM workspace_sources WHERE id=? AND workspace_id=?",
                (source_id, workspace_id),
            ).fetchone()
            if not row:
                return False
            # CASCADE will delete session_source_links
            conn.execute(
                "DELETE FROM workspace_sources WHERE id=? AND workspace_id=?",
                (source_id, workspace_id),
            )
            conn.commit()
        storage_path = row["storage_path"]
        if storage_path:
            path = Path(storage_path)
            target = path.parent if path.name else path
            with suppress(Exception):
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
        return True

    async def bulk_delete_workspace_sources(
        self,
        workspace_id: str,
        source_ids: list[str],
    ) -> dict:
        if not source_ids:
            return {"deleted_ids": [], "not_found_ids": []}

        deduped_ids = list(dict.fromkeys(source_ids))
        async with self._write_lock:
            deleted_rows, not_found_ids = await asyncio.to_thread(
                self._bulk_delete_workspace_sources_sync, workspace_id, deduped_ids
            )

        for _, storage_path in deleted_rows:
            if not storage_path:
                continue
            path = Path(storage_path)
            target = path.parent if path.name else path
            with suppress(Exception):
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)

        return {
            "deleted_ids": [row_id for row_id, _ in deleted_rows],
            "not_found_ids": not_found_ids,
        }

    def _bulk_delete_workspace_sources_sync(
        self,
        workspace_id: str,
        source_ids: list[str],
    ) -> tuple[list[tuple[str, str | None]], list[str]]:
        placeholders = ",".join("?" for _ in source_ids)
        params: list[object] = [workspace_id, *source_ids]

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, storage_path
                FROM workspace_sources
                WHERE workspace_id=? AND id IN ({placeholders})
                """,
                tuple(params),
            ).fetchall()
            deleted_rows = [(str(row["id"]), row["storage_path"]) for row in rows]
            if deleted_rows:
                deleted_ids = [row_id for row_id, _ in deleted_rows]
                delete_placeholders = ",".join("?" for _ in deleted_ids)
                conn.execute(
                    f"""
                    DELETE FROM workspace_sources
                    WHERE workspace_id=? AND id IN ({delete_placeholders})
                    """,
                    (workspace_id, *deleted_ids),
                )
                conn.commit()

        existing = {row_id for row_id, _ in deleted_rows}
        not_found_ids = [source_id for source_id in source_ids if source_id not in existing]
        return deleted_rows, not_found_ids

    async def link_source_to_session(
        self,
        *,
        session_id: str,
        source_id: str,
        workspace_id: str,
    ) -> None:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._link_source_to_session_sync,
                session_id,
                source_id,
                workspace_id,
                now,
            )

    def _link_source_to_session_sync(
        self,
        session_id: str,
        source_id: str,
        workspace_id: str,
        now: str,
    ) -> None:
        with self._connect() as conn:
            session_row = conn.execute(
                """
                SELECT workspace_id
                FROM sessions
                WHERE id=? AND archived_at IS NULL
                """,
                (session_id,),
            ).fetchone()
            if not session_row:
                raise ValueError("会话不存在")

            source_row = conn.execute(
                """
                SELECT workspace_id
                FROM workspace_sources
                WHERE id=?
                """,
                (source_id,),
            ).fetchone()
            if not source_row:
                raise ValueError("来源不存在")

            session_workspace_id = str(session_row["workspace_id"])
            source_workspace_id = str(source_row["workspace_id"])
            if session_workspace_id != workspace_id:
                raise PermissionError("会话不属于当前工作区")
            if source_workspace_id != workspace_id:
                raise PermissionError("来源不属于当前工作区")
            if session_workspace_id != source_workspace_id:
                raise PermissionError("来源与会话不在同一工作区")

            conn.execute(
                """
                INSERT OR IGNORE INTO session_source_links(session_id, source_id, linked_at)
                VALUES(?, ?, ?)
                """,
                (session_id, source_id, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            conn.commit()

    async def unlink_source_from_session(self, session_id: str, source_id: str) -> bool:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._unlink_source_from_session_sync, session_id, source_id
            )

    def _unlink_source_from_session_sync(self, session_id: str, source_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM session_source_links WHERE session_id=? AND source_id=?",
                (session_id, source_id),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (_now_iso(), session_id),
            )
            conn.commit()
        return True

    async def add_chat_message(
        self,
        *,
        workspace_id: str,
        session_id: str,
        role: str,
        content: str,
        model_meta: dict | None = None,
    ) -> None:
        now = _now_iso()
        mid = str(uuid4())
        async with self._write_lock:
            await asyncio.to_thread(
                self._add_chat_message_sync,
                workspace_id,
                session_id,
                mid,
                role,
                content,
                model_meta or {},
                now,
            )

    def _add_chat_message_sync(
        self,
        workspace_id: str,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        model_meta: dict,
        now: str,
    ) -> None:
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM sessions
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not exists:
                raise ValueError("会话不存在")
            conn.execute(
                """
                INSERT INTO session_chat_messages(
                    id, session_id, role, content, model_meta_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    json.dumps(model_meta, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            conn.commit()

    async def list_chat_messages(
        self,
        workspace_id: str,
        session_id: str,
        limit: int = 200,
        newest_first: bool = False,
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._list_chat_messages_sync, workspace_id, session_id, limit, newest_first
        )

    def _list_chat_messages_sync(
        self,
        workspace_id: str,
        session_id: str,
        limit: int,
        newest_first: bool,
    ) -> list[dict]:
        order = "DESC" if newest_first else "ASC"
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM sessions
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                f"""
                SELECT id, role, content, created_at, model_meta_json
                FROM session_chat_messages
                WHERE session_id=?
                ORDER BY created_at {order}
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "model_meta": json.loads(row["model_meta_json"] or "{}"),
            }
            for row in rows
        ]

    async def save_presentation(
        self,
        *,
        session_id: str,
        payload: dict,
        is_snapshot: bool = False,
        snapshot_label: str | None = None,
        output_mode: str | None = None,
        html_deck: dict | None = None,
    ) -> dict:
        now = _now_iso()
        pid = f"sp-{uuid4().hex[:12]}"
        async with self._write_lock:
            return await asyncio.to_thread(
                self._save_presentation_sync,
                session_id,
                pid,
                payload,
                is_snapshot,
                snapshot_label,
                output_mode,
                html_deck,
                now,
            )

    def _save_presentation_sync(
        self,
        session_id: str,
        presentation_id: str,
        payload: dict,
        is_snapshot: bool,
        snapshot_label: str | None,
        output_mode: str | None,
        html_deck: dict | None,
        now: str,
    ) -> dict:
        stored_payload = dict(payload or {})
        if output_mode:
            stored_payload["outputMode"] = output_mode
        normalized_title = str(stored_payload.get("title") or "").strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 AS next_no FROM session_presentations WHERE session_id=?",
                (session_id,),
            ).fetchone()
            version_no = int(row["next_no"]) if row else 1
            if html_deck is not None:
                artifact_meta = self._persist_html_deck_artifact_sync(
                    session_id=session_id,
                    presentation_id=presentation_id,
                    version_no=version_no,
                    html_deck=html_deck,
                    fallback_title=normalized_title or "新演示文稿",
                    now=now,
                )
                artifacts = stored_payload.get("artifacts")
                artifacts_dict = dict(artifacts) if isinstance(artifacts, dict) else {}
                artifacts_dict["html_deck"] = artifact_meta
                stored_payload["artifacts"] = artifacts_dict
            conn.execute(
                """
                INSERT INTO session_presentations(
                    id, session_id, version_no, is_snapshot, snapshot_label, payload_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    presentation_id,
                    session_id,
                    version_no,
                    1 if is_snapshot else 0,
                    snapshot_label,
                    json.dumps(stored_payload, ensure_ascii=False),
                    now,
                ),
            )
            session_row = conn.execute(
                "SELECT title_edited_by_user FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            title_edited_by_user = bool(
                session_row and int(session_row["title_edited_by_user"] or 0)
            )
            if normalized_title and not title_edited_by_user:
                conn.execute(
                    "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                    (normalized_title, now, session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at=? WHERE id=?",
                    (now, session_id),
                )
            conn.commit()
        return {
            "id": presentation_id,
            "version_no": version_no,
            "is_snapshot": is_snapshot,
            "snapshot_label": snapshot_label,
            "created_at": now,
            "presentation": stored_payload,
        }

    async def get_latest_presentation(
        self, workspace_id: str, session_id: str
    ) -> dict | None:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._get_latest_presentation_sync, workspace_id, session_id
            )

    def _get_latest_presentation_sync(
        self, workspace_id: str, session_id: str
    ) -> dict | None:
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM sessions
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not exists:
                return None
            row = conn.execute(
                """
                SELECT id, version_no, is_snapshot, snapshot_label, payload_json, created_at
                FROM session_presentations
                WHERE session_id=?
                ORDER BY version_no DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None

            payload = json.loads(row["payload_json"])
            normalized_payload, changed, repair_report = normalize_presentation_payload(payload)
            if changed:
                normalized_json = json.dumps(normalized_payload, ensure_ascii=False)
                self._update_presentation_payload_sync(conn, row["id"], normalized_json)
                logger.info(
                    "presentation_payload_repaired",
                    extra={
                        "session_id": session_id,
                        "presentation_id": row["id"],
                        "repair_applied": True,
                        "repaired_slide_count": repair_report["repaired_slide_count"],
                        "repair_types": ",".join(repair_report["repair_types"]),
                        "invalid_slide_count": repair_report["invalid_slide_count"],
                    },
                )
            elif repair_report["invalid_slide_count"] > 0:
                logger.warning(
                    "presentation_payload_contains_unrecoverable_slides",
                    extra={
                        "session_id": session_id,
                        "presentation_id": row["id"],
                        "repair_applied": False,
                        "invalid_slide_count": repair_report["invalid_slide_count"],
                    },
                )

            return {
                "id": row["id"],
                "version_no": row["version_no"],
                "is_snapshot": bool(row["is_snapshot"]),
                "snapshot_label": row["snapshot_label"],
                "created_at": row["created_at"],
                "presentation": normalized_payload,
                "output_mode": self._extract_output_mode(normalized_payload),
                "artifacts": self._extract_artifacts(normalized_payload),
            }

    @staticmethod
    def _update_presentation_payload_sync(
        conn: sqlite3.Connection,
        presentation_id: str,
        payload_json: str,
    ) -> None:
        conn.execute(
            """
            UPDATE session_presentations
            SET payload_json=?
            WHERE id=?
            """,
            (payload_json, presentation_id),
        )
        conn.commit()

    async def create_snapshot(
        self,
        *,
        workspace_id: str,
        session_id: str,
        snapshot_label: str,
        payload: dict | None = None,
    ) -> dict:
        latest = payload
        if latest is None:
            latest_row = await self.get_latest_presentation(workspace_id, session_id)
            if not latest_row:
                raise ValueError("当前会话暂无可快照内容")
            latest = latest_row["presentation"]
        return await self.save_presentation(
            session_id=session_id,
            payload=latest,
            is_snapshot=True,
            snapshot_label=snapshot_label,
            output_mode=self._extract_output_mode(latest),
        )

    async def get_latest_html_deck(
        self,
        workspace_id: str,
        session_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._get_latest_html_deck_sync,
                workspace_id,
                session_id,
            )

    def _get_latest_html_deck_sync(
        self,
        workspace_id: str,
        session_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        latest = self._get_latest_presentation_sync(workspace_id, session_id)
        if not latest:
            return None
        artifacts = self._extract_artifacts(latest.get("presentation"))
        deck = artifacts.get("html_deck") if isinstance(artifacts, dict) else None
        if not isinstance(deck, dict):
            return None
        storage_path = str(deck.get("storage_path") or "").strip()
        meta_path = str(deck.get("meta_storage_path") or "").strip()
        if not storage_path:
            return None
        html_path = Path(storage_path)
        if not html_path.exists():
            return None
        html = html_path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        if meta_path:
            meta_file = Path(meta_path)
            if meta_file.exists():
                with suppress(Exception):
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if not meta:
            meta = {
                "title": latest.get("presentation", {}).get("title") or "新演示文稿",
                "slide_count": int(deck.get("slide_count") or 0),
                "slides": [],
            }
        return html, meta

    @staticmethod
    def _extract_output_mode(payload: dict | None) -> str:
        if not isinstance(payload, dict):
            return "structured"
        raw = payload.get("outputMode")
        return str(raw).strip() if isinstance(raw, str) and str(raw).strip() else "structured"

    @staticmethod
    def _extract_artifacts(payload: dict | None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        artifacts = payload.get("artifacts")
        return dict(artifacts) if isinstance(artifacts, dict) else {}

    def _persist_html_deck_artifact_sync(
        self,
        *,
        session_id: str,
        presentation_id: str,
        version_no: int,
        html_deck: dict,
        fallback_title: str,
        now: str,
    ) -> dict[str, Any]:
        raw_html = str(html_deck.get("html") or "").strip()
        if not raw_html:
            raise ValueError("HTML deck content is empty.")
        expected_slide_count = html_deck.get("expected_slide_count")
        normalized_html, meta, _presentation = normalize_html_deck(
            html=raw_html,
            fallback_title=fallback_title,
            expected_slide_count=expected_slide_count if isinstance(expected_slide_count, int) else None,
        )
        artifact_dir = self.uploads_dir / "presentations" / session_id / presentation_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        html_path = artifact_dir / "presentation.html"
        meta_path = artifact_dir / "presentation.meta.json"
        html_path.write_text(normalized_html, encoding="utf-8")
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "version": version_no,
            "slide_count": meta["slide_count"],
            "updated_at": now,
            "storage_path": str(html_path.resolve()),
            "meta_storage_path": str(meta_path.resolve()),
        }

    async def get_planning_state(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict | None:
        return await asyncio.to_thread(
            self._get_planning_state_sync,
            workspace_id,
            session_id,
        )

    def _get_planning_state_sync(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ps.session_id,
                    ps.mode,
                    ps.status,
                    ps.brief_json,
                    ps.outline_json,
                    ps.outline_version,
                    ps.source_ids_json,
                    ps.source_digest,
                    ps.outline_stale,
                    ps.active_job_id,
                    ps.agent_workspace_root,
                    ps.agent_session_version,
                    ps.assistant_status,
                    ps.topic_suggestions_json,
                    ps.updated_at
                FROM session_planning_state ps
                JOIN sessions s ON s.id = ps.session_id
                WHERE ps.session_id=? AND s.workspace_id=? AND s.archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not row:
                return None
            return {
                "session_id": row["session_id"],
                "mode": row["mode"] or "agentic",
                "status": row["status"],
                "brief": json.loads(row["brief_json"] or "{}"),
                "outline": json.loads(row["outline_json"] or "{}"),
                "outline_version": int(row["outline_version"] or 0),
                "source_ids": json.loads(row["source_ids_json"] or "[]"),
                "source_digest": row["source_digest"] or "",
                "outline_stale": bool(row["outline_stale"]),
                "active_job_id": row["active_job_id"],
                "agent_workspace_root": row["agent_workspace_root"],
                "agent_session_version": int(row["agent_session_version"] or 0),
                "assistant_status": row["assistant_status"],
                "topic_suggestions": json.loads(row["topic_suggestions_json"] or "[]"),
                "updated_at": row["updated_at"],
            }

    async def save_planning_state(
        self,
        *,
        workspace_id: str,
        session_id: str,
        status: str,
        brief: dict | None = None,
        outline: dict | None = None,
        outline_version: int | None = None,
        source_ids: list[str] | None = None,
        source_digest: str | None = None,
        outline_stale: bool | None = None,
        active_job_id: str | None = None,
        mode: str | None = None,
        agent_workspace_root: str | None = None,
        agent_session_version: int | None = None,
        assistant_status: str | None = None,
        topic_suggestions: list[dict] | None = None,
    ) -> dict:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._save_planning_state_sync,
                workspace_id,
                session_id,
                status,
                brief,
                outline,
                outline_version,
                source_ids,
                source_digest,
                outline_stale,
                active_job_id,
                mode,
                agent_workspace_root,
                agent_session_version,
                assistant_status,
                topic_suggestions,
                now,
            )
        state = await self.get_planning_state(workspace_id, session_id)
        if state is None:
            raise ValueError("会话 planning state 保存失败")
        return state

    def _save_planning_state_sync(
        self,
        workspace_id: str,
        session_id: str,
        status: str,
        brief: dict | None,
        outline: dict | None,
        outline_version: int | None,
        source_ids: list[str] | None,
        source_digest: str | None,
        outline_stale: bool | None,
        active_job_id: str | None,
        mode: str | None,
        agent_workspace_root: str | None,
        agent_session_version: int | None,
        assistant_status: str | None,
        topic_suggestions: list[dict] | None,
        now: str,
    ) -> None:
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM sessions
                WHERE id=? AND workspace_id=? AND archived_at IS NULL
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not exists:
                raise ValueError("会话不存在")

            current = conn.execute(
                """
                SELECT mode, status, brief_json, outline_json, outline_version, source_ids_json,
                       source_digest, outline_stale, active_job_id, agent_workspace_root,
                       agent_session_version, assistant_status, topic_suggestions_json
                FROM session_planning_state
                WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
            merged_mode = mode or (current["mode"] if current else "agentic")
            merged_status = status or (current["status"] if current else "collecting_requirements")
            merged_brief = brief if brief is not None else json.loads(current["brief_json"] or "{}") if current else {}
            merged_outline = outline if outline is not None else json.loads(current["outline_json"] or "{}") if current else {}
            merged_outline_version = (
                int(outline_version)
                if outline_version is not None
                else int(current["outline_version"] or 0) if current else 0
            )
            merged_source_ids = (
                list(source_ids)
                if source_ids is not None
                else json.loads(current["source_ids_json"] or "[]") if current else []
            )
            merged_source_digest = (
                str(source_digest)
                if source_digest is not None
                else str(current["source_digest"] or "") if current else ""
            )
            merged_outline_stale = (
                bool(outline_stale)
                if outline_stale is not None
                else bool(current["outline_stale"]) if current else False
            )
            merged_active_job_id = (
                active_job_id
                if active_job_id is not None
                else current["active_job_id"] if current else None
            )
            merged_agent_workspace_root = (
                agent_workspace_root
                if agent_workspace_root is not None
                else current["agent_workspace_root"] if current else None
            )
            merged_agent_session_version = (
                int(agent_session_version)
                if agent_session_version is not None
                else int(current["agent_session_version"] or 0) if current else 0
            )
            merged_assistant_status = (
                assistant_status
                if assistant_status is not None
                else current["assistant_status"] if current else None
            )
            merged_topic_suggestions = (
                list(topic_suggestions)
                if topic_suggestions is not None
                else json.loads(current["topic_suggestions_json"] or "[]") if current else []
            )
            conn.execute(
                """
                INSERT INTO session_planning_state(
                    session_id, mode, status, brief_json, outline_json, outline_version,
                    source_ids_json, source_digest, outline_stale, active_job_id,
                    agent_workspace_root, agent_session_version, assistant_status,
                    topic_suggestions_json, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    mode=excluded.mode,
                    status=excluded.status,
                    brief_json=excluded.brief_json,
                    outline_json=excluded.outline_json,
                    outline_version=excluded.outline_version,
                    source_ids_json=excluded.source_ids_json,
                    source_digest=excluded.source_digest,
                    outline_stale=excluded.outline_stale,
                    active_job_id=excluded.active_job_id,
                    agent_workspace_root=excluded.agent_workspace_root,
                    agent_session_version=excluded.agent_session_version,
                    assistant_status=excluded.assistant_status,
                    topic_suggestions_json=excluded.topic_suggestions_json,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    merged_mode,
                    merged_status,
                    json.dumps(merged_brief, ensure_ascii=False),
                    json.dumps(merged_outline, ensure_ascii=False),
                    merged_outline_version,
                    json.dumps(merged_source_ids, ensure_ascii=False),
                    merged_source_digest,
                    1 if merged_outline_stale else 0,
                    merged_active_job_id,
                    merged_agent_workspace_root,
                    merged_agent_session_version,
                    merged_assistant_status,
                    json.dumps(merged_topic_suggestions, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
            conn.commit()

    async def save_generation_job(
        self, job_id: str, session_id: str, status: str
    ) -> None:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._save_generation_job_sync, job_id, session_id, status, now
            )

    def _save_generation_job_sync(
        self, job_id: str, session_id: str, status: str, now: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generation_jobs(job_id, session_id, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at
                """,
                (job_id, session_id, status, now, now),
            )
            conn.commit()

    async def update_generation_job_status(self, job_id: str, status: str) -> None:
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._update_generation_job_status_sync, job_id, status, now
            )

    async def set_generated_title_if_unedited(
        self,
        workspace_id: str,
        session_id: str,
        title: str,
    ) -> None:
        normalized = str(title or "").strip()
        if not normalized:
            return
        now = _now_iso()
        async with self._write_lock:
            await asyncio.to_thread(
                self._set_generated_title_if_unedited_sync,
                workspace_id,
                session_id,
                normalized,
                now,
            )

    def _set_generated_title_if_unedited_sync(
        self,
        workspace_id: str,
        session_id: str,
        title: str,
        now: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET title=?, updated_at=?
                WHERE id=? AND workspace_id=? AND title_edited_by_user=0
                """,
                (title, now, session_id, workspace_id),
            )
            conn.commit()

    def _update_generation_job_status_sync(self, job_id: str, status: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE generation_jobs SET status=?, updated_at=? WHERE job_id=?",
                (status, now, job_id),
            )
            conn.commit()

    async def get_latest_generation_job(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict | None:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._get_latest_generation_job_sync,
                workspace_id,
                session_id,
            )

    def _get_latest_generation_job_sync(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT gj.job_id, gj.status, gj.updated_at
                FROM generation_jobs gj
                JOIN sessions s ON s.id = gj.session_id
                WHERE gj.session_id=? AND s.workspace_id=? AND s.archived_at IS NULL
                ORDER BY gj.updated_at DESC
                LIMIT 1
                """,
                (session_id, workspace_id),
            ).fetchone()
            if not row:
                return None
            return {
                "job_id": row["job_id"],
                "status": row["status"],
                "updated_at": row["updated_at"],
            }

    @staticmethod
    def _row_to_session_summary(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "title": row["title"],
            "title_edited_by_user": bool(row["title_edited_by_user"]),
            "status": row["status"],
            "is_pinned": bool(row["is_pinned"]),
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_opened_at": row["last_opened_at"],
            "source_count": int(row["source_count"] or 0),
            "chat_count": int(row["chat_count"] or 0),
            "has_presentation": bool(row["has_presentation"]),
        }

    @staticmethod
    def _row_to_source_meta(row: sqlite3.Row) -> dict:
        linked_count = row["linked_session_count"] if "linked_session_count" in row.keys() else None
        return {
            "id": row["id"],
            "name": row["name"],
            "type": row["source_type"],
            "fileCategory": row["file_category"],
            "size": row["size"],
            "status": row["status"],
            "previewSnippet": row["preview_snippet"],
            "error": row["error"],
            "created_at": row["created_at"],
            "linked_session_count": int(linked_count) if linked_count is not None else None,
        }
