# coding=utf-8
"""
通知去重 sidecar SQLite
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


class DedupStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "state" / "notification_dedup.db"
        self.schema_path = Path(__file__).with_name("schema.sql")
        self._conn: sqlite3.Connection | None = None
        self.busy_timeout_ms = 30_000
        self.max_write_retries = 5
        self.retry_base_delay_seconds = 0.1

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_write_with_retry(self._initialize_once)

    def _initialize_once(self) -> None:
        conn = self._get_connection()
        self._ensure_base_table(conn)
        self._migrate_schema(conn)
        with open(self.schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

    def _ensure_base_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_notification_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                platform_id TEXT NOT NULL,
                platform_name TEXT DEFAULT '',
                region_type TEXT NOT NULL,
                match_policy TEXT NOT NULL,
                title TEXT NOT NULL,
                dedup_key TEXT DEFAULT '',
                normalized_title TEXT NOT NULL,
                url TEXT DEFAULT '',
                normalized_url TEXT DEFAULT '',
                fact_signature_json TEXT DEFAULT '{}',
                embedding_blob BLOB,
                sent_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sent_notification_records)")
        }
        if "dedup_key" not in columns:
            conn.execute(
                "ALTER TABLE sent_notification_records "
                "ADD COLUMN dedup_key TEXT DEFAULT ''"
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dedup_key "
            "ON sent_notification_records(dedup_key)"
        )

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                timeout=self.busy_timeout_ms / 1000,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        return self._conn

    def purge_expired(self, now_str: str) -> int:
        return self._run_write_with_retry(lambda: self._purge_expired_once(now_str))

    def _purge_expired_once(self, now_str: str) -> int:
        now_ts = self._to_epoch_seconds(now_str)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sent_notification_records WHERE expires_at < ?",
            (now_ts,),
        )
        conn.commit()
        return cursor.rowcount

    def fetch_recent_records(self, now_str: str, window_hours: int) -> List[Dict]:
        self.purge_expired(now_str)
        now_ts = self._to_epoch_seconds(now_str)
        lower_bound = now_ts - int(timedelta(hours=window_hours).total_seconds())
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM sent_notification_records
            WHERE expires_at >= ?
              AND sent_at >= ?
            ORDER BY sent_at DESC
            """,
            (now_ts, lower_bound),
        )
        return [dict(row) for row in cursor.fetchall()]

    def insert_records(self, records: List[Dict]) -> int:
        if not records:
            return 0
        return self._run_write_with_retry(lambda: self._insert_records_once(records))

    def _insert_records_once(self, records: List[Dict]) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO sent_notification_records (
                source_type, platform_id, platform_name, region_type, match_policy,
                title, dedup_key, normalized_title, url, normalized_url, fact_signature_json,
                embedding_blob, sent_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.get("source_type", ""),
                    record.get("platform_id", ""),
                    record.get("platform_name", ""),
                    record.get("region_type", ""),
                    record.get("match_policy", ""),
                    record.get("title", ""),
                    record.get("dedup_key", ""),
                    record.get("normalized_title", ""),
                    record.get("url", ""),
                    record.get("normalized_url", ""),
                    record.get("fact_signature_json", "{}"),
                    record.get("embedding_blob"),
                    self._to_epoch_seconds(record.get("sent_at")),
                    self._to_epoch_seconds(record.get("expires_at")),
                )
                for record in records
            ],
        )
        conn.commit()
        return len(records)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _run_write_with_retry(self, func):
        for attempt in range(self.max_write_retries):
            try:
                return func()
            except sqlite3.OperationalError as exc:
                if not self._is_retryable_lock_error(exc) or attempt == self.max_write_retries - 1:
                    raise
                if self._conn is not None:
                    self._conn.rollback()
                time.sleep(self.retry_base_delay_seconds * (2 ** attempt))

    @staticmethod
    def _is_retryable_lock_error(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return (
            "database is locked" in message
            or "database table is locked" in message
            or "database schema is locked" in message
        )

    @staticmethod
    def _to_epoch_seconds(value: Any) -> int:
        if value is None:
            raise ValueError("timestamp value is required")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, str):
            normalized = value.strip()
            dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp())
        raise TypeError(f"unsupported timestamp value: {value!r}")
