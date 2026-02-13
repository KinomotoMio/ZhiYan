"""SQLite 会话存储层（workspace/session/source/presentation/chat）。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4


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
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
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

                CREATE INDEX IF NOT EXISTS idx_sessions_workspace_updated
                ON sessions(workspace_id, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sources_session_created
                ON session_sources(session_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_chat_session_created
                ON session_chat_messages(session_id, created_at ASC);

                CREATE INDEX IF NOT EXISTS idx_presentation_session_version
                ON session_presentations(session_id, version_no DESC);
                """
            )
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
                    id, workspace_id, title, status, is_pinned,
                    created_at, updated_at, last_opened_at
                ) VALUES(?, ?, ?, 'active', 0, ?, ?, ?)
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
                  (SELECT COUNT(*) FROM session_sources ss WHERE ss.session_id=s.id) AS source_count,
                  (SELECT COUNT(*) FROM session_chat_messages cm WHERE cm.session_id=s.id) AS chat_count
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
                  (SELECT COUNT(*) FROM session_sources ss WHERE ss.session_id=s.id) AS source_count,
                  (SELECT COUNT(*) FROM session_chat_messages cm WHERE cm.session_id=s.id) AS chat_count
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
            conn.execute(
                """
                INSERT INTO session_sources(
                    id, session_id, source_type, name, file_category, size, status,
                    preview_snippet, storage_path, parsed_content, metadata_json,
                    error, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    session_id,
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
                """
                SELECT * FROM session_sources
                WHERE id=? AND session_id=?
                """,
                (source_id, session_id),
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
                SELECT * FROM session_sources
                WHERE session_id=?
                ORDER BY created_at DESC
                """,
                (session_id,),
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
                SELECT ss.parsed_content
                FROM session_sources ss
                JOIN sessions s ON s.id = ss.session_id
                WHERE ss.id=? AND ss.session_id=? AND s.workspace_id=? AND s.archived_at IS NULL
                """,
                (source_id, session_id, workspace_id),
            ).fetchone()
        return None if row is None else (row["parsed_content"] or "")

    async def delete_source(
        self, workspace_id: str, session_id: str, source_id: str
    ) -> bool:
        async with self._write_lock:
            return await asyncio.to_thread(
                self._delete_source_sync, workspace_id, session_id, source_id
            )

    def _delete_source_sync(self, workspace_id: str, session_id: str, source_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ss.storage_path
                FROM session_sources ss
                JOIN sessions s ON s.id=ss.session_id
                WHERE ss.id=? AND ss.session_id=? AND s.workspace_id=? AND s.archived_at IS NULL
                """,
                (source_id, session_id, workspace_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "DELETE FROM session_sources WHERE id=? AND session_id=?",
                (source_id, session_id),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (_now_iso(), session_id),
            )
            conn.commit()
        storage_path = row["storage_path"]
        if storage_path:
            path = Path(storage_path)
            # Files are stored under data/uploads/<source_id>/filename, delete the whole source folder.
            target = path.parent if path.name else path
            with suppress(Exception):
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
        return True

    async def get_combined_source_content(
        self, workspace_id: str, session_id: str, source_ids: list[str]
    ) -> str:
        return await asyncio.to_thread(
            self._get_combined_source_content_sync, workspace_id, session_id, source_ids
        )

    def _get_combined_source_content_sync(
        self, workspace_id: str, session_id: str, source_ids: list[str]
    ) -> str:
        if not source_ids:
            return ""
        placeholders = ",".join("?" for _ in source_ids)
        params: list[object] = [session_id, workspace_id, *source_ids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ss.id, ss.parsed_content
                FROM session_sources ss
                JOIN sessions s ON s.id=ss.session_id
                WHERE ss.session_id=? AND s.workspace_id=? AND ss.id IN ({placeholders})
                """,
                tuple(params),
            ).fetchall()
        row_map = {row["id"]: (row["parsed_content"] or "") for row in rows}
        parts = [row_map[sid] for sid in source_ids if row_map.get(sid)]
        return "\n\n---\n\n".join(parts)

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
                now,
            )

    def _save_presentation_sync(
        self,
        session_id: str,
        presentation_id: str,
        payload: dict,
        is_snapshot: bool,
        snapshot_label: str | None,
        now: str,
    ) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 AS next_no FROM session_presentations WHERE session_id=?",
                (session_id,),
            ).fetchone()
            version_no = int(row["next_no"]) if row else 1
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
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
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
        }

    async def get_latest_presentation(
        self, workspace_id: str, session_id: str
    ) -> dict | None:
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
        return {
            "id": row["id"],
            "version_no": row["version_no"],
            "is_snapshot": bool(row["is_snapshot"]),
            "snapshot_label": row["snapshot_label"],
            "created_at": row["created_at"],
            "presentation": json.loads(row["payload_json"]),
        }

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
        )

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

    def _update_generation_job_status_sync(self, job_id: str, status: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE generation_jobs SET status=?, updated_at=? WHERE job_id=?",
                (status, now, job_id),
            )
            conn.commit()

    @staticmethod
    def _row_to_session_summary(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "title": row["title"],
            "status": row["status"],
            "is_pinned": bool(row["is_pinned"]),
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_opened_at": row["last_opened_at"],
            "source_count": int(row["source_count"] or 0),
            "chat_count": int(row["chat_count"] or 0),
        }

    @staticmethod
    def _row_to_source_meta(row: sqlite3.Row) -> dict:
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
        }
