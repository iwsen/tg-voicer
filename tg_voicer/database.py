"""
SQLite database management for TG-Voicer.
Stores processed voice notes, status, text transcripts, and chat cursors.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    """Thread-safe SQLite database manager for tracking voice messages and cursors."""

    def __init__(self, db_path: str | Path = "data/voicer.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for high performance concurrent reads and writes
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    chat_id INTEGER NOT NULL,
                    msg_id INTEGER NOT NULL,
                    media_type TEXT,
                    sender_id INTEGER,
                    sender_name TEXT,
                    chat_title TEXT,
                    chat_type TEXT,
                    transcription_id INTEGER,
                    text TEXT,
                    status TEXT NOT NULL,  -- 'done', 'pending', 'failed', 'skipped'
                    error_message TEXT,
                    is_live INTEGER DEFAULT 0,
                    duration_sec REAL DEFAULT 0,
                    msg_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, msg_id)
                );

                CREATE INDEX IF NOT EXISTS idx_proc_status ON processed_messages(status);
                CREATE INDEX IF NOT EXISTS idx_proc_chat_id ON processed_messages(chat_id);
                CREATE INDEX IF NOT EXISTS idx_proc_created_at ON processed_messages(created_at);

                CREATE TABLE IF NOT EXISTS chat_cursors (
                    chat_id INTEGER PRIMARY KEY,
                    chat_title TEXT,
                    chat_type TEXT,
                    oldest_scanned_id INTEGER,
                    newest_scanned_id INTEGER,
                    total_scanned INTEGER DEFAULT 0,
                    total_voice_found INTEGER DEFAULT 0,
                    total_transcribed INTEGER DEFAULT 0,
                    history_completed INTEGER DEFAULT 0,
                    last_scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_kv (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def is_message_processed(self, chat_id: int, msg_id: int) -> bool:
        """Check if message is already recorded and completed."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM processed_messages WHERE chat_id = ? AND msg_id = ?",
            (chat_id, msg_id),
        )
        row = cur.fetchone()
        if not row:
            return False
        return row["status"] in ("done", "skipped")

    def get_message(self, chat_id: int, msg_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM processed_messages WHERE chat_id = ? AND msg_id = ?",
            (chat_id, msg_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def save_message(
        self,
        chat_id: int,
        msg_id: int,
        media_type: str,
        sender_id: Optional[int] = None,
        sender_name: Optional[str] = None,
        chat_title: Optional[str] = None,
        chat_type: Optional[str] = None,
        transcription_id: Optional[int] = None,
        text: Optional[str] = None,
        status: str = "done",
        error_message: Optional[str] = None,
        is_live: bool = False,
        duration_sec: float = 0.0,
        msg_date: Optional[datetime] = None,
    ) -> None:
        """Insert or replace message state in database."""
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO processed_messages (
                    chat_id, msg_id, media_type, sender_id, sender_name,
                    chat_title, chat_type, transcription_id, text, status,
                    error_message, is_live, duration_sec, msg_date,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, msg_id) DO UPDATE SET
                    text = coalesce(excluded.text, processed_messages.text),
                    transcription_id = coalesce(excluded.transcription_id, processed_messages.transcription_id),
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (
                    chat_id,
                    msg_id,
                    media_type,
                    sender_id,
                    sender_name,
                    chat_title,
                    chat_type,
                    transcription_id,
                    text,
                    status,
                    error_message,
                    1 if is_live else 0,
                    duration_sec,
                    msg_date.isoformat() if msg_date else None,
                ),
            )

    def update_transcription(
        self,
        chat_id: int,
        msg_id: int,
        transcription_id: Optional[int],
        text: str,
        status: str = "done",
    ) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                UPDATE processed_messages
                SET transcription_id = coalesce(?, transcription_id),
                    text = ?,
                    status = ?,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ? AND msg_id = ?
                """,
                (transcription_id, text, status, chat_id, msg_id),
            )

    def mark_message_failed(self, chat_id: int, msg_id: int, error_message: str) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                UPDATE processed_messages
                SET status = 'failed',
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ? AND msg_id = ?
                """,
                (error_message, chat_id, msg_id),
            )

    def mark_message_skipped(self, chat_id: int, msg_id: int, reason: str) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO processed_messages (
                    chat_id, msg_id, status, error_message, updated_at
                ) VALUES (?, ?, 'skipped', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, msg_id) DO UPDATE SET
                    status = 'skipped',
                    error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chat_id, msg_id, reason),
            )

    def get_chat_cursor(self, chat_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM chat_cursors WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_chat_cursor(
        self,
        chat_id: int,
        chat_title: Optional[str] = None,
        chat_type: Optional[str] = None,
        oldest_scanned_id: Optional[int] = None,
        newest_scanned_id: Optional[int] = None,
        history_completed: Optional[bool] = None,
        increment_scanned: int = 0,
        increment_voice: int = 0,
        increment_transcribed: int = 0,
    ) -> None:
        conn = self._get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM chat_cursors WHERE chat_id = ?", (chat_id,))
            existing = cur.fetchone()

            if not existing:
                cur.execute(
                    """
                    INSERT INTO chat_cursors (
                        chat_id, chat_title, chat_type, oldest_scanned_id, newest_scanned_id,
                        total_scanned, total_voice_found, total_transcribed,
                        history_completed, last_scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        chat_id,
                        chat_title,
                        chat_type,
                        oldest_scanned_id,
                        newest_scanned_id,
                        increment_scanned,
                        increment_voice,
                        increment_transcribed,
                        1 if history_completed else 0,
                    ),
                )
            else:
                # Update existing cursor bounds
                cur_oldest = existing["oldest_scanned_id"]
                if oldest_scanned_id is not None:
                    if cur_oldest is None or oldest_scanned_id < cur_oldest:
                        cur_oldest = oldest_scanned_id

                cur_newest = existing["newest_scanned_id"]
                if newest_scanned_id is not None:
                    if cur_newest is None or newest_scanned_id > cur_newest:
                        cur_newest = newest_scanned_id

                comp = existing["history_completed"]
                if history_completed is not None:
                    comp = 1 if history_completed else 0

                cur.execute(
                    """
                    UPDATE chat_cursors SET
                        chat_title = coalesce(?, chat_title),
                        chat_type = coalesce(?, chat_type),
                        oldest_scanned_id = ?,
                        newest_scanned_id = ?,
                        total_scanned = total_scanned + ?,
                        total_voice_found = total_voice_found + ?,
                        total_transcribed = total_transcribed + ?,
                        history_completed = ?,
                        last_scanned_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                    """,
                    (
                        chat_title,
                        chat_type,
                        cur_oldest,
                        cur_newest,
                        increment_scanned,
                        increment_voice,
                        increment_transcribed,
                        comp,
                        chat_id,
                    ),
                )

    def reset_all_cursors(self) -> int:
        """Reset history cursors to allow re-scanning all chats."""
        conn = self._get_connection()
        with conn:
            cur = conn.cursor()
            cur.execute("UPDATE chat_cursors SET oldest_scanned_id = NULL, history_completed = 0")
            return cur.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate stats about processed messages."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT count(*) as cnt FROM processed_messages WHERE status = 'done'")
        done_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM processed_messages WHERE status = 'pending'")
        pending_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM processed_messages WHERE status = 'failed'")
        failed_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM processed_messages WHERE status = 'skipped'")
        skipped_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM processed_messages WHERE is_live = 1")
        live_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM chat_cursors WHERE history_completed = 1")
        completed_chats_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT count(*) as cnt FROM chat_cursors")
        total_chats_cnt = cur.fetchone()["cnt"]

        return {
            "transcribed_done": done_cnt,
            "transcribed_pending": pending_cnt,
            "failed": failed_cnt,
            "skipped": skipped_cnt,
            "live_captured": live_cnt,
            "chats_total": total_chats_cnt,
            "chats_history_completed": completed_chats_cnt,
        }

    def get_recent_transcriptions(self, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT chat_id, msg_id, chat_title, sender_name, media_type,
                   duration_sec, text, status, is_live, updated_at
            FROM processed_messages
            WHERE text IS NOT NULL AND text != ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
