# coding=utf-8

import unittest
from datetime import datetime

from trendradar.websocket.core.client import WebSocketChannelClient


class WebSocketClientTest(unittest.TestCase):
    def test_now_returns_timezone_aware_datetime(self):
        now = _FakeChannel._now()
        self.assertIsNotNone(now.tzinfo)


class _FakeChannel(WebSocketChannelClient):
    def __init__(self):
        super().__init__(
            name="fake",
            url="wss://example.test/socket",
            logger=_FakeLogger(),
            event_callback=lambda event: None,
        )

    async def handle_message(self, message) -> None:
        return None


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None
