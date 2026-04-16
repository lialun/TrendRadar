# coding=utf-8

import tempfile
import unittest
from unittest.mock import patch

from trendradar.dedup.service import DedupService


class FakeEmbedder:
    is_available = False

    def encode(self, texts):
        return []


class FakeReranker:
    is_available = False

    def score_pairs(self, pairs):
        return []


class DedupServiceTest(unittest.TestCase):
    def test_exact_only_filtering_still_works_without_models(self):
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

            filtered = service.filter_before_send(
                stats=[],
                new_titles={},
                rss_items=None,
                rss_new_items=None,
                standalone_data=None,
                now_str="2026-04-15 10:00:00",
            )

            self.assertIn("stats", filtered)

    def test_standalone_is_filtered_when_same_item_already_kept_in_complex_region(self):
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
            standalone_data = {
                "platforms": [
                    {
                        "id": "zhihu",
                        "name": "知乎",
                        "items": [{"title": "OpenAI 发布新模型", "url": "https://example.com/1"}],
                    }
                ],
                "rss_feeds": [],
            }

            filtered = service.filter_before_send(
                stats=stats,
                new_titles={},
                rss_items=None,
                rss_new_items=None,
                standalone_data=standalone_data,
                now_str="2026-04-15 10:00:00",
            )

            self.assertEqual(1, len(filtered["stats"][0]["titles"]))
            self.assertEqual([], filtered["standalone_data"]["platforms"])

    def test_standalone_keeps_same_title_from_different_sources(self):
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

            standalone_data = {
                "platforms": [
                    {
                        "id": "zhihu",
                        "name": "知乎",
                        "items": [{"title": "OpenAI 发布新模型", "url": "https://example.com/1"}],
                    },
                    {
                        "id": "wallstreetcn-hot",
                        "name": "华尔街见闻",
                        "items": [{"title": "OpenAI 发布新模型", "url": "https://example.com/1"}],
                    },
                ],
                "rss_feeds": [],
            }

            filtered = service.filter_before_send(
                stats=[],
                new_titles={},
                rss_items=None,
                rss_new_items=None,
                standalone_data=standalone_data,
                now_str="2026-04-15 10:00:00",
            )

            self.assertEqual(2, len(filtered["standalone_data"]["platforms"]))

    def test_filter_logs_summary_and_debug_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DedupService.from_components(
                base_dir=tmpdir,
                config={
                    "ENABLED": True,
                    "WINDOW_HOURS": 72,
                    "TOP_K": 20,
                    "RERANK_THRESHOLD": 0.82,
                    "STRICT_TIME_CONFLICT": True,
                    "DEBUG": True,
                },
                embedder=FakeEmbedder(),
                reranker=FakeReranker(),
            )

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
            standalone_data = {
                "platforms": [
                    {
                        "id": "zhihu",
                        "name": "知乎",
                        "items": [{"title": "OpenAI 发布新模型", "url": "https://example.com/1"}],
                    }
                ],
                "rss_feeds": [],
            }

            with patch("builtins.print") as print_mock:
                service.filter_before_send(
                    stats=stats,
                    new_titles={},
                    rss_items=None,
                    rss_new_items=None,
                    standalone_data=standalone_data,
                    now_str="2026-04-15 10:00:00",
                )

            printed = "\n".join(" ".join(str(arg) for arg in call.args) for call in print_mock.call_args_list)
            self.assertIn("[Dedup] candidates:", printed)
            self.assertIn("[Dedup] filtered:", printed)
            self.assertIn("[Dedup] remaining:", printed)
            self.assertIn("[Dedup][DEBUG] drop", printed)
