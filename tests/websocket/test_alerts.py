# coding=utf-8

import unittest

from trendradar.websocket.pipeline.alerts import WebSocketAlertManager


class FakeSender:
    enabled = True

    def __init__(self):
        self.sent = []

    def send_text(self, content: str) -> bool:
        self.sent.append(content)
        return True


class AlertManagerTest(unittest.TestCase):
    def test_alerts_are_rate_limited_by_key_and_cooldown(self):
        sender = FakeSender()
        manager = WebSocketAlertManager(sender, logger=_FakeLogger(), cooldown_seconds=1800, enabled=True)

        first = manager.notify_failure("jin10:disconnect", "failed")
        second = manager.notify_failure("jin10:disconnect", "failed again")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(1, len(sender.sent))


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None
