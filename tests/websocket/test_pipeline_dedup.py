# coding=utf-8

import unittest

from trendradar.websocket.models import RealtimeEvent
from trendradar.websocket.pipeline.dedup import RealtimeDedupAdapter


class RealtimeDedupAdapterTest(unittest.TestCase):
    def test_build_candidate_uses_fact_signature_dict_directly(self):
        adapter = RealtimeDedupAdapter(dedup_service=None)

        candidate = adapter.build_candidate(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                source_message_id="1",
                dedup_key="jin10:1",
                title="法国CPI为2%",
            )
        )

        self.assertIsInstance(candidate.fact_signature, dict)
        self.assertIn("percentages", candidate.fact_signature)
