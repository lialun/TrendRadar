# coding=utf-8

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from trendradar.websocket.models import RealtimeEvent
from trendradar.websocket.runtime import RealtimePipeline, WebSocketRuntime


class RealtimePipelineTest(unittest.TestCase):
    def test_runtime_pipeline_processes_event_and_records_success(self):
        pipeline = RealtimePipeline(
            dedup_adapter=_FakeDedupAdapter(),
            feishu_sender=_FakeSender(),
            logger=_FakeLogger(),
            now_func=lambda: datetime(2026, 4, 16, 10, 0, 0),
        )

        ok = pipeline.process_event(
            RealtimeEvent(channel="jin10", event_type="1000", source_message_id="1", dedup_key="jin10:1", title="标题")
        )

        self.assertTrue(ok)
        self.assertEqual(1, pipeline.stats["sent_success"])

    def test_runtime_parses_naive_snapshot_time_without_crashing(self):
        runtime = WebSocketRuntime(
            config={
                "ENABLED": True,
                "QUEUE_MAX_SIZE": 10,
                "HEALTH_LOG_INTERVAL_SECONDS": 300,
                "LOGGING": {"LEVEL": "INFO", "FILE": "", "MAX_SIZE_MB": 1, "BACKUP_COUNT": 1},
                "ALERTS": {
                    "ENABLED": False,
                    "FAILURE_THRESHOLD": 5,
                    "OUTAGE_SECONDS": 600,
                    "PROTOCOL_ERROR_THRESHOLD": 20,
                    "QUEUE_BACKLOG_THRESHOLD": 100,
                    "COOLDOWN_SECONDS": 1800,
                    "WEBHOOK_URL": "",
                },
                "CHANNELS": {},
            },
            dedup_service=MagicMock(),
            feishu_webhook="",
            max_accounts=1,
            now_func=lambda: datetime.fromisoformat("2026-04-16T10:10:00+08:00"),
        )
        runtime.channels = {
            "jin10": _FakeChannel(
                {
                    "connected": False,
                    "ever_connected": True,
                    "message_count": 1,
                    "news_count": 1,
                    "heartbeat_count": 0,
                    "error_count": 0,
                    "protocol_error_count": 0,
                    "consecutive_protocol_errors": 0,
                    "consecutive_failures": 0,
                    "total_reconnects": 0,
                    "last_message_time": "2026-04-16T10:00:00",
                    "last_error": "",
                    "extra": {},
                }
            )
        }

        runtime._evaluate_alerts()


class _FakeCandidate:
    title = "标题"


class _FakeDedupAdapter:
    def check(self, event, now_str):
        return _FakeCandidate(), None

    def record_sent(self, candidate, now_str=None):
        return 1


class _FakeSender:
    def send_event(self, event):
        return True


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _FakeChannel:
    def __init__(self, stats):
        self._stats = stats

    def get_stats(self):
        return dict(self._stats)
