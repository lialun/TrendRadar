# coding=utf-8

import tempfile
import unittest
from pathlib import Path

from trendradar.websocket.config import load_websocket_config


class WebSocketConfigTest(unittest.TestCase):
    def test_load_websocket_config_reads_nested_main_config(self):
        config = load_websocket_config(
            {
                "websocket": {
                    "enabled": True,
                    "processing": {"queue_max_size": 123},
                    "channels": {
                        "jin10": {
                            "enabled": True,
                            "url": "wss://example.test/socket",
                            "reconnect": {
                                "initial_delay": 2,
                                "max_delay": 33,
                            },
                        }
                    },
                }
            }
        )

        self.assertTrue(config["ENABLED"])
        self.assertEqual(123, config["QUEUE_MAX_SIZE"])
        self.assertEqual("wss://example.test/socket", config["CHANNELS"]["jin10"]["URL"])
        self.assertEqual(33, config["CHANNELS"]["jin10"]["RECONNECT"]["MAX_DELAY"])

    def test_load_websocket_config_falls_back_to_legacy_websocket_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            legacy_file = config_dir / "websocket.yaml"
            legacy_file.write_text(
                "\n".join(
                    [
                        "global:",
                        "  enabled: true",
                        "  heartbeat_interval: 30",
                        "  heartbeat_timeout: 10",
                        "sources:",
                        "  jin10:",
                        "    enabled: true",
                        "    url: wss://legacy.test/socket",
                        "    reconnect:",
                        "      initial_delay: 3",
                        "      max_delay: 90",
                        "processing:",
                        "  queue:",
                        "    max_size: 888",
                        "monitoring:",
                        "  stats_interval: 222",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_websocket_config({}, config_dir=str(config_dir))

            self.assertTrue(config["ENABLED"])
            self.assertEqual(888, config["QUEUE_MAX_SIZE"])
            self.assertEqual(222, config["HEALTH_LOG_INTERVAL_SECONDS"])
            self.assertEqual("wss://legacy.test/socket", config["CHANNELS"]["jin10"]["URL"])
            self.assertEqual(90, config["CHANNELS"]["jin10"]["RECONNECT"]["MAX_DELAY"])

    def test_load_websocket_config_reads_simplified_websocket_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            runtime_file = config_dir / "websocket.yaml"
            runtime_file.write_text(
                "\n".join(
                    [
                        "enabled: true",
                        "channels:",
                        "  jin10:",
                        "    enabled: true",
                        "    url: wss://runtime.test/socket",
                        "processing:",
                        "  queue_max_size: 321",
                        "monitoring:",
                        "  health_log_interval_seconds: 123",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_websocket_config({}, config_dir=str(config_dir))

            self.assertTrue(config["ENABLED"])
            self.assertEqual(321, config["QUEUE_MAX_SIZE"])
            self.assertEqual(123, config["HEALTH_LOG_INTERVAL_SECONDS"])
            self.assertEqual("wss://runtime.test/socket", config["CHANNELS"]["jin10"]["URL"])
