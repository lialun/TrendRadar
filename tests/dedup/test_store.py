# coding=utf-8

import sqlite3
import tempfile
import unittest

from trendradar.dedup.store import DedupStore


class DedupStoreTest(unittest.TestCase):
    def test_insert_query_and_expire_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.initialize()
            inserted = store.insert_records(
                [
                    {
                        "source_type": "hotlist",
                        "platform_id": "weibo",
                        "platform_name": "微博",
                        "region_type": "hotlist",
                        "match_policy": "semantic",
                        "title": "OpenAI 发布新模型",
                        "normalized_title": "openai发布新模型",
                        "url": "https://example.com/1",
                        "normalized_url": "https://example.com/1",
                        "fact_signature_json": "{}",
                        "embedding_blob": b"[]",
                        "sent_at": "2026-04-15 10:00:00",
                        "expires_at": "2026-04-18 10:00:00",
                    },
                    {
                        "source_type": "hotlist",
                        "platform_id": "zhihu",
                        "platform_name": "知乎",
                        "region_type": "hotlist",
                        "match_policy": "semantic",
                        "title": "Old News",
                        "normalized_title": "oldnews",
                        "url": "https://example.com/old",
                        "normalized_url": "https://example.com/old",
                        "fact_signature_json": "{}",
                        "embedding_blob": b"[]",
                        "sent_at": "2026-04-10 10:00:00",
                        "expires_at": "2026-04-20 10:00:00",
                    }
                ]
            )

            rows = store.fetch_recent_records("2026-04-15 12:00:00", 72)
            self.assertEqual(2, inserted)
            self.assertEqual(1, len(rows))
            self.assertEqual("OpenAI 发布新模型", rows[0]["title"])

            deleted = store.purge_expired("2026-04-18 10:00:01")
            rows = store.fetch_recent_records("2026-04-18 10:00:01", 72)
            self.assertEqual(1, deleted)
            self.assertEqual(0, len(rows))

    def test_initialize_migrates_existing_db_with_dedup_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(store.db_path))
            conn.execute(
                """
                CREATE TABLE sent_notification_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    platform_id TEXT NOT NULL,
                    platform_name TEXT DEFAULT '',
                    region_type TEXT NOT NULL,
                    match_policy TEXT NOT NULL,
                    title TEXT NOT NULL,
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
            conn.commit()
            conn.close()

            store.initialize()

            conn = sqlite3.connect(str(store.db_path))
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(sent_notification_records)")
            }
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(sent_notification_records)")
            }
            conn.close()

            self.assertIn("dedup_key", columns)
            self.assertIn("idx_dedup_key", indexes)

    def test_connection_enables_wal_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.initialize()

            conn = store._get_connection()
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

            self.assertEqual("wal", str(journal_mode).lower())
            self.assertEqual(store.busy_timeout_ms, busy_timeout)

    def test_insert_records_retries_when_database_is_locked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.initialize()

            records = [
                {
                    "source_type": "websocket",
                    "platform_id": "jin10",
                    "platform_name": "jin10",
                    "region_type": "websocket_realtime",
                    "match_policy": "exact_or_semantic",
                    "title": "retry",
                    "dedup_key": "jin10:1",
                    "normalized_title": "retry",
                    "url": "",
                    "normalized_url": "",
                    "fact_signature_json": "{}",
                    "embedding_blob": b"",
                    "sent_at": "2026-04-16 10:00:00",
                    "expires_at": "2026-04-18 10:00:00",
                }
            ]

            original = store._insert_records_once
            attempts = {"count": 0}

            def flaky_insert(rows):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise sqlite3.OperationalError("database is locked")
                return original(rows)

            store._insert_records_once = flaky_insert
            inserted = store.insert_records(records)

            self.assertEqual(1, inserted)
            self.assertEqual(2, attempts["count"])
