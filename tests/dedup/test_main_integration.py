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
    def test_send_flow_records_after_success(self):
        analyzer = NewsAnalyzer.__new__(NewsAnalyzer)
        analyzer.report_mode = "current"
        analyzer.proxy_url = None
        analyzer.update_info = None
        analyzer.frequency_file = None
        analyzer.dedup_service = MagicMock()
        analyzer.dedup_service.filter_before_send.return_value = {
            "stats": [
                {
                    "word": "AI",
                    "count": 1,
                    "titles": [{"title": "OpenAI 发布新模型", "source_id": "weibo", "source_name": "微博"}],
                }
            ],
            "new_titles": {},
            "rss_items": None,
            "rss_new_items": None,
            "standalone_data": None,
        }
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
        analyzer.dedup_service.filter_before_send.assert_called_once()
        analyzer.dedup_service.record_after_send.assert_called_once()
