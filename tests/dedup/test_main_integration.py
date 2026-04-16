# coding=utf-8

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

litellm_stub = types.ModuleType("litellm")
litellm_stub.completion = MagicMock()
sys.modules.setdefault("litellm", litellm_stub)

from trendradar.__main__ import NewsAnalyzer


class MainIntegrationTest(unittest.TestCase):
    def test_analysis_pipeline_dedups_before_ai_and_html(self):
        analyzer = NewsAnalyzer.__new__(NewsAnalyzer)
        analyzer.filter_method = "keyword"
        analyzer.frequency_file = None
        analyzer.interests_file = None
        analyzer.update_info = None
        analyzer.dedup_service = MagicMock()
        analyzer.dedup_service.filter_before_send.return_value = {
            "stats": [
                {
                    "word": "AI",
                    "count": 1,
                    "titles": [{"title": "Deduped News", "source_id": "weibo", "source_name": "微博"}],
                }
            ],
            "new_titles": {},
            "rss_items": None,
            "rss_new_items": None,
            "standalone_data": None,
        }
        analyzer._run_ai_analysis = MagicMock(return_value="ai-result")
        analyzer.ctx = MagicMock()
        analyzer.ctx.display_mode = "keyword"
        analyzer.ctx.config = {
            "AI_ANALYSIS": {"ENABLED": True},
            "AI_TRANSLATION": {"ENABLED": False},
            "STORAGE": {"FORMATS": {"HTML": True}},
            "SHOW_VERSION_UPDATE": False,
        }
        analyzer.ctx.count_frequency.return_value = (
            [{"word": "AI", "count": 2, "titles": [{"title": "Raw News"}]}],
            2,
        )
        analyzer.ctx.weight_config = {}
        analyzer.ctx.rank_threshold = 5
        analyzer.ctx.get_time.return_value = __import__("datetime").datetime(2026, 4, 15, 10, 0, 0)
        analyzer.ctx.generate_html = MagicMock(return_value="output/test.html")
        analyzer._get_mode_strategy = MagicMock(return_value={"report_type": "当前榜单"})

        result = analyzer._run_analysis_pipeline(
            data_source={"weibo": {"Raw News": {"ranks": [1]}}},
            mode="current",
            title_info={},
            new_titles={},
            word_groups=[],
            filter_words=[],
            id_to_name={"weibo": "微博"},
            failed_ids=[],
            global_filters=[],
            rss_items=None,
            rss_new_items=None,
            standalone_data=None,
            schedule=SimpleNamespace(push=True, analyze=True),
            rss_new_urls=None,
        )

        self.assertEqual("Deduped News", result[0][0]["titles"][0]["title"])
        analyzer._run_ai_analysis.assert_called_once()
        analyzer.ctx.generate_html.assert_called_once()
        self.assertEqual("Deduped News", analyzer._run_ai_analysis.call_args.args[0][0]["titles"][0]["title"])

    def test_send_flow_records_after_success(self):
        analyzer = NewsAnalyzer.__new__(NewsAnalyzer)
        analyzer.report_mode = "current"
        analyzer.proxy_url = None
        analyzer.update_info = None
        analyzer.frequency_file = None
        analyzer.dedup_service = MagicMock()
        analyzer._has_notification_configured = MagicMock(return_value=True)
        analyzer._has_valid_content = MagicMock(side_effect=lambda stats, new_titles=None: bool(stats))
        analyzer.ctx = MagicMock()
        analyzer.ctx.config = {
            "ENABLE_NOTIFICATION": True,
            "SHOW_VERSION_UPDATE": False,
            "AI_ANALYSIS": {"ENABLED": False},
        }
        analyzer.ctx.prepare_report.return_value = {"stats": []}
        dispatcher = MagicMock()
        dispatcher.dispatch_all.return_value = {"feishu": True}
        analyzer.ctx.create_notification_dispatcher.return_value = dispatcher
        analyzer.ctx.get_time.return_value = __import__("datetime").datetime(2026, 4, 15, 10, 0, 0)

        result = analyzer._send_notification_if_needed(
            stats=[{"word": "AI", "count": 1, "titles": [{"title": "OpenAI 发布新模型"}]}],
            report_type="当前榜单",
            mode="current",
            new_titles={},
            id_to_name={"weibo": "微博"},
            standalone_data=None,
            schedule=SimpleNamespace(push=True, once_push=False, period_key=None),
        )

        self.assertTrue(result)
        analyzer.dedup_service.record_after_send.assert_called_once()
