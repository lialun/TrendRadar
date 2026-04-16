# coding=utf-8

import sys
import types
import unittest

sys.modules.setdefault("litellm", types.SimpleNamespace(completion=lambda *args, **kwargs: None))

from trendradar.websocket.testing import build_jin10_test_runtime


class TestingEntrypointTest(unittest.TestCase):
    def test_build_jin10_test_runtime_returns_runtime_and_stats_printer(self):
        config = {
            "TIMEZONE": "Asia/Shanghai",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "",
            "MAX_ACCOUNTS_PER_CHANNEL": 3,
            "FEISHU_WEBHOOK_URL": "",
            "STORAGE": {
                "LOCAL": {"DATA_DIR": "output", "RETENTION_DAYS": 0},
                "REMOTE": {"RETENTION_DAYS": 0},
                "PULL": {"ENABLED": False, "DAYS": 7},
                "BACKEND": "auto",
                "FORMATS": {"TXT": True, "HTML": False},
            },
            "DEDUP": {"ENABLED": False},
            "WEBSOCKET": {
                "ENABLED": True,
                "QUEUE_MAX_SIZE": 10,
                "HEALTH_LOG_INTERVAL_SECONDS": 300,
                "LOGGING": {"LEVEL": "INFO", "FILE": "", "MAX_SIZE_MB": 1, "BACKUP_COUNT": 1},
                "ALERTS": {"ENABLED": False, "WEBHOOK_URL": "", "COOLDOWN_SECONDS": 1800},
                "CHANNELS": {
                    "jin10": {
                        "ENABLED": True,
                        "URL": "wss://example.test/socket",
                        "HEARTBEAT_INTERVAL": 30,
                        "HEARTBEAT_TIMEOUT": 10,
                        "RECONNECT": {"INITIAL_DELAY": 1, "MAX_DELAY": 2, "BACKOFF_FACTOR": 2.0},
                        "PROTOCOL": {},
                    }
                },
            },
        }

        runtime, printer = build_jin10_test_runtime(config)

        self.assertIsNotNone(runtime)
        self.assertTrue(callable(printer))
