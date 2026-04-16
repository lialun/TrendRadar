# coding=utf-8

import unittest

from trendradar.websocket.models import RealtimeEvent
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

    def test_render_event_keeps_link_when_only_content_exists(self):
        sender = RealtimeFeishuSender(
            "",
            logger=_FakeLogger(),
        )

        rendered = sender.render_event(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                content="纯正文，没有标题字段",
                published_at="2026-04-16 21:00:42",
                detail_url="https://flash.jin10.com/detail/1",
                meta={"msg_id": 1000},
            )
        )

        self.assertIn("(https://flash.jin10.com/detail/1)", rendered)
        self.assertIn("[纯正文，没有标题字段]", rendered)

    def test_render_event_keeps_link_when_only_title_exists(self):
        sender = RealtimeFeishuSender(
            "",
            logger=_FakeLogger(),
        )

        rendered = sender.render_event(
            RealtimeEvent(
                channel="jin10",
                event_type="1000",
                title="只有标题",
                published_at="2026-04-16 21:00:42",
                detail_url="https://flash.jin10.com/detail/2",
                meta={"msg_id": 1000},
            )
        )

        self.assertIn("(https://flash.jin10.com/detail/2)", rendered)
        self.assertIn("[只有标题]", rendered)


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None
