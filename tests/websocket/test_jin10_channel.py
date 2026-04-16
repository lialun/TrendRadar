# coding=utf-8

import unittest

from trendradar.websocket.channels.jin10.channel import Jin10Channel


class Jin10ChannelTest(unittest.TestCase):
    def test_jin10_channel_turns_flash_message_into_realtime_event(self):
        channel = Jin10Channel(
            {"URL": "wss://example.test/socket"},
            logger=_FakeLogger(),
            event_callback=lambda event: None,
        )

        event = channel._build_realtime_event(
            msg_id=1000,
            payload={
                "id": 123,
                "time": "2026-04-16 10:00:00",
                "data": {"title": "标题A", "content": "正文B"},
                "action": 1,
            },
        )

        self.assertEqual("jin10:123", event.dedup_key)
        self.assertEqual("标题A", event.title)
        self.assertEqual("正文B", event.content)

    def test_key_exchange_accepts_packet_with_extra_trailing_bytes(self):
        channel = Jin10Channel(
            {"URL": "wss://example.test/socket"},
            logger=_FakeLogger(),
            event_callback=lambda event: None,
        )

        async def _run():
            channel.ws = _FakeWebSocket()
            await channel._handle_key_exchange(
                bytes.fromhex("01000000020000000300000004000000")
            )

        import asyncio
        asyncio.run(_run())

        self.assertEqual("3.2", channel.encryption_key)

    def test_key_exchange_requires_minimum_packet_length(self):
        channel = Jin10Channel(
            {"URL": "wss://example.test/socket"},
            logger=_FakeLogger(),
            event_callback=lambda event: None,
        )

        with self.assertRaises(ValueError):
            import asyncio
            asyncio.run(channel._handle_key_exchange(b"short"))


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


class _FakeWebSocket:
    async def send(self, payload):
        return None
