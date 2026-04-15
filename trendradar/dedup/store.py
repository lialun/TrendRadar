# coding=utf-8
"""
通知去重 sidecar SQLite
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


class DedupStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "state" / "notification_dedup.db"
        self.schema_path = Path(__file__).with_name("schema.sql")
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        with open(self.schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def purge_expired(self, now_str: str) -> int:
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
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO sent_notification_records (
                source_type, platform_id, platform_name, region_type, match_policy,
                title, normalized_title, url, normalized_url, fact_signature_json,
                embedding_blob, sent_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.get("source_type", ""),
                    record.get("platform_id", ""),
                    record.get("platform_name", ""),
                    record.get("region_type", ""),
                    record.get("match_policy", ""),
                    record.get("title", ""),
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
