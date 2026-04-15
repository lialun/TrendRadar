# coding=utf-8

import unittest

from trendradar.dedup.filters import flatten_candidates, rebuild_filtered_payload


class FilterTest(unittest.TestCase):
    def test_standalone_duplicate_is_removed_after_complex_region_accepts(self):
        stats = [
            {
                "word": "AI",
                "count": 1,
                "position": 0,
                "titles": [
                    {
                        "title": "OpenAI 发布新模型",
                        "url": "https://example.com/1",
                        "source_name": "微博",
                        "source_id": "weibo",
                    }
                ],
            }
        ]
        standalone = {
            "platforms": [
                {
                    "id": "weibo",
                    "name": "微博",
                    "items": [{"title": "OpenAI 发布新模型", "url": "https://example.com/1"}],
                }
            ],
            "rss_feeds": [],
        }

        candidates = flatten_candidates(
            stats=stats,
            new_titles={},
            rss_items=None,
            rss_new_items=None,
            standalone_data=standalone,
        )
        accepted_ids = {candidates[0].candidate_id}
        payload = rebuild_filtered_payload(candidates, accepted_ids)

        self.assertEqual(1, len(payload["stats"][0]["titles"]))
        self.assertEqual([], payload["standalone_data"]["platforms"])
