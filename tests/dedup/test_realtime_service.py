# coding=utf-8

import tempfile
import unittest

from trendradar.dedup.models import CandidateNews
from trendradar.dedup.service import DedupService


class FakeEmbedder:
    is_available = False

    def encode(self, texts):
        return []


class FakeReranker:
    is_available = False

    def score_pairs(self, pairs):
        return []


class DedupRealtimeServiceTest(unittest.TestCase):
    def test_check_realtime_candidate_uses_dedup_key_before_exact_matching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DedupService.from_components(
                base_dir=tmpdir,
                config={
                    "ENABLED": True,
                    "WINDOW_HOURS": 72,
                    "TOP_K": 20,
                    "RERANK_THRESHOLD": 0.82,
                    "STRICT_TIME_CONFLICT": True,
                },
                embedder=FakeEmbedder(),
                reranker=FakeReranker(),
            )

            sent_candidate = CandidateNews(
                candidate_id="websocket:jin10:1",
                source_type="websocket",
                platform_id="jin10",
                platform_name="jin10",
                region_type="websocket_realtime",
                match_policy="exact_or_semantic",
                title="标题A",
                dedup_key="jin10:1",
                normalized_title="标题a",
            )
            duplicate_candidate = CandidateNews(
                candidate_id="websocket:jin10:1:retry",
                source_type="websocket",
                platform_id="jin10",
                platform_name="jin10",
                region_type="websocket_realtime",
                match_policy="exact_or_semantic",
                title="标题B",
                dedup_key="jin10:1",
                normalized_title="标题b",
            )

            inserted = service.record_realtime_candidate(
                sent_candidate,
                now_str="2026-04-16 10:00:00",
            )
            duplicate = service.check_realtime_candidate(
                duplicate_candidate,
                now_str="2026-04-16 10:01:00",
            )

            self.assertEqual(1, inserted)
            self.assertIsNotNone(duplicate)
            self.assertEqual("dedup_key", duplicate["reason"])
