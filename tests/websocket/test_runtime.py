# coding=utf-8

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from trendradar.websocket.models import RealtimeEvent
from trendradar.websocket.runtime import RealtimePipeline, WebSocketRuntime


class RealtimePipelineTest(unittest.TestCase):
    def test_runtime_pipeline_processes_event_and_records_success(self):
        logger = _CollectingLogger()
        pipeline = RealtimePipeline(
            dedup_adapter=_FakeDedupAdapter(),
            feishu_sender=_FakeSender(),
            logger=logger,
            now_func=lambda: datetime(2026, 4, 16, 10, 0, 0),
        )

        ok = pipeline.process_event(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                source_message_id="1",
                dedup_key="jin10:1",
                title="标题",
                content="完整的正文内容",
            )
        )

        self.assertTrue(ok)
        self.assertEqual(1, pipeline.stats["sent_success"])
        self.assertEqual(1, len(logger.info_messages))
        self.assertIn("summary=完整的正文内容", logger.info_messages[0])
        self.assertNotIn("title=", logger.info_messages[0])
        self.assertNotIn("\n", logger.info_messages[0])

    def test_runtime_pipeline_logs_full_duplicate_diagnostics(self):
        content = "这是一条需要完整保留的正文，用于确认 duplicate 日志不会再被截断，后半段也必须完整出现在日志里。"
        logger = _CollectingLogger()
        pipeline = RealtimePipeline(
            dedup_adapter=_FakeDedupAdapter(
                duplicate={
                    "reason": "semantic",
                    "scope": "semantic",
                    "matched_title": "历史匹配标题",
                    "matched_region": "websocket_realtime",
                    "matched_platform_id": "jin10",
                    "matched_dedup_key": "jin10:old",
                    "matched_url": "https://flash.jin10.com/detail/old",
                    "matched_normalized_title": "历史匹配标题",
                    "matched_fact_signature": {"numbers": ["17"], "negation": False},
                    "score": 0.9784,
                }
            ),
            feishu_sender=_FakeSender(),
            logger=logger,
            now_func=lambda: datetime(2026, 4, 16, 10, 0, 0),
        )

        ok = pipeline.process_event(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                source_message_id="1",
                dedup_key="jin10:1",
                title="标题",
                content=content,
                published_at="2026-04-17 10:06:31",
                detail_url="https://flash.jin10.com/detail/1",
                meta={"msg_id": 1000},
            )
        )

        self.assertFalse(ok)
        self.assertEqual(1, pipeline.stats["filtered_duplicate"])
        self.assertEqual(1, len(logger.info_messages))
        message = logger.info_messages[0]
        self.assertIn("reason=semantic scope=semantic", message)
        self.assertIn(f"content={content}", message)
        self.assertIn("matched_title=历史匹配标题", message)
        self.assertIn("matched_fact_signature={\"negation\": false, \"numbers\": [\"17\"]}", message)
        self.assertIn("score=0.9784", message)

    def test_runtime_pipeline_logs_full_send_failed_diagnostics(self):
        logger = _CollectingLogger()
        pipeline = RealtimePipeline(
            dedup_adapter=_FakeDedupAdapter(),
            feishu_sender=_FakeSender(send_ok=False, label="news", enabled=False, target_count=0),
            logger=logger,
            now_func=lambda: datetime(2026, 4, 16, 10, 0, 0),
        )

        ok = pipeline.process_event(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                source_message_id="1",
                dedup_key="jin10:1",
                title="只有标题",
                content="发送失败时也要保留完整正文",
                published_at="2026-04-17 10:10:00",
                detail_url="https://flash.jin10.com/detail/1",
                meta={"msg_id": 1000},
            )
        )

        self.assertFalse(ok)
        self.assertEqual(1, pipeline.stats["sent_failed"])
        self.assertEqual(1, len(logger.warning_messages))
        message = logger.warning_messages[0]
        self.assertIn("sender_label=news", message)
        self.assertIn("sender_enabled=False", message)
        self.assertIn("sender_targets=0", message)
        self.assertIn("content=发送失败时也要保留完整正文", message)
        self.assertIn("normalized_title=发送失败时也要保留完整正文", message)

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
    def __init__(self, title="标题", normalized_title="标题", fact_signature=None):
        self.title = title
        self.normalized_title = normalized_title
        self.fact_signature = fact_signature or {}


class _FakeDedupAdapter:
    def __init__(self, candidate=None, duplicate=None):
        self.candidate = candidate
        self.duplicate = duplicate

    def check(self, event, now_str):
        candidate = self.candidate or _FakeCandidate(
            title=event.content or event.title,
            normalized_title=event.content or event.title,
            fact_signature={},
        )
        return candidate, self.duplicate

    def record_sent(self, candidate, now_str=None):
        return 1


class _FakeSender:
    def __init__(self, send_ok=True, label="news", enabled=True, target_count=1):
        self.send_ok = send_ok
        self.label = label
        self.enabled = enabled
        self.target_count = target_count

    def send_event(self, event):
        return self.send_ok


class _CollectingLogger:
    def __init__(self):
        self.info_messages = []
        self.warning_messages = []

    @staticmethod
    def _render(args):
        if not args:
            return ""
        message = args[0]
        if len(args) > 1:
            return message % args[1:]
        return str(message)

    def info(self, *args, **kwargs):
        self.info_messages.append(self._render(args))

    def warning(self, *args, **kwargs):
        self.warning_messages.append(self._render(args))

    def exception(self, *args, **kwargs):
        return None


class _FakeChannel:
    def __init__(self, stats):
        self._stats = stats

    def get_stats(self):
        return dict(self._stats)
