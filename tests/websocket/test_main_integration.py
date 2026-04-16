# coding=utf-8

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("litellm", types.SimpleNamespace(completion=lambda *args, **kwargs: None))

from trendradar.__main__ import NewsAnalyzer


def _build_test_config():
    return {
        "PLATFORMS": [],
        "TIMEZONE": "Asia/Shanghai",
        "REQUEST_INTERVAL": 100,
        "REPORT_MODE": "daily",
        "USE_PROXY": False,
        "DEFAULT_PROXY": "",
        "STORAGE": {
            "LOCAL": {"DATA_DIR": "output", "RETENTION_DAYS": 0},
            "REMOTE": {"RETENTION_DAYS": 0},
            "PULL": {"ENABLED": False, "DAYS": 7},
            "BACKEND": "auto",
            "FORMATS": {"TXT": True, "HTML": False},
        },
        "DEDUP": {"ENABLED": False},
        "WEBSOCKET": {"ENABLED": True},
        "DEBUG": False,
        "FEISHU_WEBHOOK_URL": "",
        "MAX_ACCOUNTS_PER_CHANNEL": 3,
    }


class MainIntegrationTest(unittest.TestCase):
    @patch("trendradar.__main__.build_websocket_runtime")
    @patch("trendradar.context.AppContext.create_dedup_service")
    @patch.object(NewsAnalyzer, "_init_storage_manager")
    def test_news_analyzer_starts_and_stops_websocket_runtime(
        self,
        init_storage_manager_mock,
        create_dedup_service_mock,
        build_runtime_mock,
    ):
        runtime = MagicMock()
        runtime.start.return_value = True
        build_runtime_mock.return_value = runtime
        create_dedup_service_mock.return_value = MagicMock()
        init_storage_manager_mock.return_value = None

        analyzer = NewsAnalyzer(config=_build_test_config())

        with patch.object(analyzer, "_initialize_and_check_config"), \
                patch.object(analyzer, "_crawl_data", return_value=({}, {}, [])), \
                patch.object(analyzer, "_crawl_rss_data", return_value=(None, None, None, set())), \
                patch.object(analyzer, "_execute_mode_strategy"):
            analyzer.run()

        runtime.start.assert_called_once()
        runtime.stop.assert_called_once()
