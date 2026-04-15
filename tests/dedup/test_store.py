# coding=utf-8

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
