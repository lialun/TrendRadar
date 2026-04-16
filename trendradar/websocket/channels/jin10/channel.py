# coding=utf-8
"""
Jin10 binary websocket channel implementation.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from trendradar.websocket.channels.jin10.binary_protocol import (
    BinaryReader,
    BinaryWriter,
    xor_decrypt,
    xor_encrypt,
)
from trendradar.websocket.core.client import WebSocketChannelClient
from trendradar.websocket.models import RealtimeEvent


class Jin10Channel(WebSocketChannelClient):
    KEY_EXCHANGE_PACKET_MIN_LENGTH = 12
    MAX_LAST_LIST_COUNT = 1000

    MSG_ID_NEWS_FLASH = 1000
    MSG_ID_EVENTS_FLASH = 1001
    MSG_ID_VOICE_NEWS = 1002
    MSG_ID_OPINION_NEWS = 1003
    MSG_ID_TOP_LIST = 1005
    MSG_ID_VIP_NEWS_FLASH = 1100
    MSG_ID_VIP_IMPORTANT_FLASH = 1110
    MSG_ID_LAST_NEWS_LIST = 1200
    MSG_ID_HEARTBEAT = 1201
    MSG_ID_GET_RILI_BY_DATE = 2001
    MSG_ID_USER_LOGIN_NEWS = 4002

    def __init__(self, config: Dict[str, Any], logger, event_callback):
        super().__init__(
            name="jin10",
            url=config.get("URL", ""),
            logger=logger,
            event_callback=event_callback,
            heartbeat_interval=int(config.get("HEARTBEAT_INTERVAL", 30)),
            heartbeat_timeout=int(config.get("HEARTBEAT_TIMEOUT", 10)),
            reconnect_config=config.get("RECONNECT", {}),
        )
        self.protocol = config.get("PROTOCOL", {})
        self.is_vip = bool(config.get("IS_VIP", False))
        self.encryption_key = ""
        self.last_flash_id = ""

    def connect_headers(self) -> Dict[str, str]:
        return {
            "Origin": self.protocol.get("ORIGIN", "https://www.jin10.com"),
            "User-Agent": self.protocol.get(
                "USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            ),
        }

    async def after_connect(self) -> None:
        self.encryption_key = ""
        self.snapshot.extra["has_encryption_key"] = False

    async def handle_message(self, message) -> None:
        if not isinstance(message, bytes):
            self.logger.warning(
                "[websocket][jin10] non_binary_message type=%s",
                type(message).__name__,
            )
            return

        try:
            if not self.encryption_key:
                await self._handle_key_exchange(message)
                self.snapshot.consecutive_protocol_errors = 0
                return

            decrypted = xor_decrypt(message, self.encryption_key)
            await self._parse_message(decrypted)
            self.snapshot.consecutive_protocol_errors = 0
        except Exception as exc:
            if self.record_protocol_error("handle_message", exc):
                raise RuntimeError("protocol error threshold exceeded") from exc

    async def send_heartbeat(self) -> None:
        return None

    async def _handle_key_exchange(self, message: bytes) -> None:
        if len(message) < self.KEY_EXCHANGE_PACKET_MIN_LENGTH:
            raise ValueError(
                f"unexpected key exchange packet length: {len(message)}"
            )
        reader = BinaryReader(message)
        reader.read_u32()
        param2 = reader.read_u32()
        param3 = reader.read_u32()
        self.encryption_key = f"{param3}.{param2}"
        self.snapshot.extra["has_encryption_key"] = True
        self.logger.info("[websocket][jin10] key_exchange_success")
        await self._send_login()

    async def _send_login(self) -> None:
        if self.ws is None:
            return

        writer = BinaryWriter()
        writer.write_i16(self.MSG_ID_USER_LOGIN_NEWS)
        writer.write_u32(0)
        writer.write_string("")
        writer.write_string(
            self.protocol.get(
                "USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
        )
        writer.write_u32(1 if self.is_vip else 0)
        writer.write_string("web")
        if self.last_flash_id:
            writer.write_string(str(self.last_flash_id))

        await self.ws.send(xor_encrypt(writer.to_bytes(), self.encryption_key))
        self.logger.info(
            "[websocket][jin10] login_sent incremental=%s last_flash_id=%s",
            bool(self.last_flash_id),
            self.last_flash_id or "-",
        )

    async def _parse_message(self, data: bytes) -> None:
        reader = BinaryReader(data)
        msg_id = reader.read_i16()

        if msg_id == self.MSG_ID_HEARTBEAT:
            self.snapshot.heartbeat_count += 1
            if self.ws is not None:
                await self.ws.send(b"")
            return

        if msg_id in {
            self.MSG_ID_NEWS_FLASH,
            self.MSG_ID_VIP_NEWS_FLASH,
            self.MSG_ID_VIP_IMPORTANT_FLASH,
            self.MSG_ID_EVENTS_FLASH,
            self.MSG_ID_USER_LOGIN_NEWS,
            self.MSG_ID_VOICE_NEWS,
            self.MSG_ID_OPINION_NEWS,
            self.MSG_ID_TOP_LIST,
        }:
            payload = json.loads(reader.read_string())
            if msg_id == self.MSG_ID_USER_LOGIN_NEWS:
                self._handle_login_response(payload)
                return
            if msg_id == self.MSG_ID_TOP_LIST:
                self.logger.info("[websocket][jin10] top_list_received")
                return
            if msg_id in {self.MSG_ID_VOICE_NEWS, self.MSG_ID_OPINION_NEWS}:
                self.logger.info("[websocket][jin10] ignored_message msg_id=%s", msg_id)
                return
            if isinstance(payload, dict) and payload.get("event") == "flash-hot-changed":
                self._handle_hot_changed(payload, msg_id)
                return
            self._handle_flash_payload(payload, msg_id, history=False)
            return

        if msg_id == self.MSG_ID_LAST_NEWS_LIST:
            count = reader.read_i32()
            if count < 0 or count > self.MAX_LAST_LIST_COUNT:
                raise ValueError(f"invalid last list count: {count}")
            items = [json.loads(reader.read_string()) for _ in range(count)]
            items.reverse()
            is_full = reader.read_i32() == 1
            self.logger.info(
                "[websocket][jin10] last_list_received count=%s full=%s",
                count,
                is_full,
            )
            for item in items:
                self._handle_flash_payload(item, msg_id, history=True)
            return

        if msg_id == self.MSG_ID_GET_RILI_BY_DATE:
            self.logger.info("[websocket][jin10] calendar_message_ignored")
            return

        self.logger.info("[websocket][jin10] unknown_message msg_id=%s", msg_id)

    def _handle_login_response(self, payload: Dict[str, Any]) -> None:
        status = payload.get("status")
        message = payload.get("message", "")
        self.logger.info(
            "[websocket][jin10] login_response status=%s message=%s",
            status,
            message,
        )

    def _handle_hot_changed(self, payload: Dict[str, Any], msg_id: int) -> None:
        items = payload.get("data", [])
        for item in items:
            event = self._build_realtime_event(msg_id=msg_id, payload=item)
            if event is not None:
                self.emit_event(event)

    def _handle_flash_payload(self, payload: Dict[str, Any], msg_id: int, *, history: bool) -> None:
        action = payload.get("action")
        if action != 1:
            self.logger.info(
                "[websocket][jin10] ignored_action action=%s msg_id=%s news_id=%s",
                action,
                msg_id,
                payload.get("id"),
            )
            return

        event = self._build_realtime_event(msg_id=msg_id, payload=payload, history=history)
        if event is None:
            return
        self.last_flash_id = event.source_message_id or self.last_flash_id
        self.snapshot.extra["last_flash_id"] = self.last_flash_id
        self.emit_event(event)

    def _build_realtime_event(
        self,
        *,
        msg_id: int,
        payload: Dict[str, Any],
        history: bool = False,
    ) -> RealtimeEvent | None:
        data = payload.get("data", {}) or {}
        source_message_id = str(payload.get("id", "") or "")
        title = str(data.get("title", "") or "").strip()
        content = str(data.get("content", "") or "").strip()
        if not title and not content:
            self.logger.info(
                "[websocket][jin10] empty_news_payload msg_id=%s news_id=%s",
                msg_id,
                source_message_id or "-",
            )
            return None

        return RealtimeEvent(
            channel="jin10",
            event_type=str(msg_id),
            source_message_id=source_message_id,
            dedup_key=f"jin10:{source_message_id}" if source_message_id else "",
            title=title,
            content=content,
            published_at=str(payload.get("time", "") or ""),
            detail_url=f"https://flash.jin10.com/detail/{source_message_id}" if source_message_id else "",
            raw_payload=dict(payload),
            meta={
                "msg_id": msg_id,
                "important": payload.get("important"),
                "type": payload.get("type"),
                "action": payload.get("action"),
                "history": history,
                "vip_title": data.get("vip_title", ""),
            },
        )

    def get_stats(self) -> Dict:
        stats = super().get_stats()
        stats["extra"].update(
            {
                "has_encryption_key": bool(self.encryption_key),
                "last_flash_id": self.last_flash_id,
            }
        )
        return stats
