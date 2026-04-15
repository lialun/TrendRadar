# coding=utf-8

import unittest

from trendradar.dedup.matcher import (
    is_exact_duplicate,
    is_semantic_duplicate,
    is_standalone_duplicate,
    select_top_k_candidates,
)


class MatcherTest(unittest.TestCase):
    def test_exact_duplicate_by_url(self):
        left = {
            "normalized_url": "https://example.com/1",
            "normalized_title": "a",
            "platform_id": "weibo",
            "source_type": "hotlist",
        }
        right = {
            "normalized_url": "https://example.com/1",
            "normalized_title": "b",
            "platform_id": "zhihu",
            "source_type": "hotlist",
        }
        self.assertTrue(is_exact_duplicate(left, right, require_same_source=False))
        self.assertFalse(is_standalone_duplicate(left, right))

    def test_semantic_duplicate_requires_no_fact_conflict(self):
        current = {
            "title": "法国CPI反弹",
            "fact_signature": {
                "numbers": [],
                "percentages": [],
                "money": [],
                "time": [],
                "negation": False,
            },
        }
        candidate = {
            "title": "法国CPI上行",
            "fact_signature": {
                "numbers": [],
                "percentages": [],
                "money": [],
                "time": [],
                "negation": False,
            },
        }
        self.assertTrue(
            is_semantic_duplicate(
                current=current,
                candidate=candidate,
                rerank_score=0.9,
                rerank_threshold=0.82,
                strict_time_conflict=True,
            )
        )

    def test_select_top_k_candidates_orders_by_similarity(self):
        candidates = [
            {"embedding": [1.0, 0.0], "title": "a"},
            {"embedding": [0.8, 0.2], "title": "b"},
            {"embedding": [0.0, 1.0], "title": "c"},
        ]
        selected = select_top_k_candidates([1.0, 0.0], candidates, top_k=2)
        self.assertEqual(["a", "b"], [item["title"] for item in selected])
