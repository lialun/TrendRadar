# coding=utf-8

import unittest

from trendradar.websocket.pipeline.feishu import RealtimeFeishuSender


class RealtimeFeishuSenderTest(unittest.TestCase):
    def test_send_text_returns_true_when_any_account_succeeds(self):
        sender = RealtimeFeishuSender(
            "https://a.test;https://b.test",
            logger=_FakeLogger(),
            max_accounts=3,
        )

        seen = []

        def _send_one(url, content):
            seen.append(url)
            return url.endswith("a.test")

        sender._send_one = _send_one

        ok = sender.send_text("content")

        self.assertTrue(ok)
        self.assertEqual(2, len(seen))


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None
