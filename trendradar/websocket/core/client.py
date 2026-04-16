# coding=utf-8
"""
Generic websocket client base for realtime channels.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Dict, Optional

import websockets
from websockets.exceptions import WebSocketException

from trendradar.websocket.core.channel import RealtimeChannel
from trendradar.websocket.core.reconnect import ReconnectController
from trendradar.websocket.models import ChannelSnapshot, RealtimeEvent


class WebSocketChannelClient(RealtimeChannel, ABC):
    def __init__(
        self,
        *,
        name: str,
        url: str,
        logger,
        event_callback: Callable[[RealtimeEvent], None],
        heartbeat_interval: int = 30,
        heartbeat_timeout: int = 10,
        reconnect_config: Optional[Dict] = None,
        protocol_error_reconnect_threshold: int = 20,
    ):
        self.name = name
        self.url = url
        self.logger = logger
        self.event_callback = event_callback
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.protocol_error_reconnect_threshold = protocol_error_reconnect_threshold
        reconnect_config = reconnect_config or {}
        self.reconnect = ReconnectController(
            initial_delay=float(reconnect_config.get("INITIAL_DELAY", 1.0)),
            max_delay=float(reconnect_config.get("MAX_DELAY", 60.0)),
            backoff_factor=float(reconnect_config.get("BACKOFF_FACTOR", 2.0)),
        )
        self.snapshot = ChannelSnapshot(name=name)
        self.ws = None
        self._stop_requested = False
        self._stop_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @abstractmethod
    async def handle_message(self, message) -> None:
        raise NotImplementedError

    def connect_headers(self) -> Dict[str, str]:
        return {}

    async def after_connect(self) -> None:
        return None

    async def send_heartbeat(self) -> None:
        return None

    def record_protocol_error(self, reason: str, exc: Exception) -> bool:
        self.snapshot.error_count += 1
        self.snapshot.protocol_error_count += 1
        self.snapshot.consecutive_protocol_errors += 1
        self.snapshot.last_error = f"{reason}: {type(exc).__name__}: {exc}"
        self.logger.warning(
            "[websocket][%s] protocol_error reason=%s consecutive=%s error=%s",
            self.name,
            reason,
            self.snapshot.consecutive_protocol_errors,
            self.snapshot.last_error,
        )
        return self.snapshot.consecutive_protocol_errors >= self.protocol_error_reconnect_threshold

    def emit_event(self, event: RealtimeEvent) -> None:
        self.snapshot.news_count += 1
        self.event_callback(event)

    @staticmethod
    def _now() -> datetime:
        return datetime.now().astimezone()

    async def connect(self) -> bool:
        try:
            self.ws = await websockets.connect(
                self.url,
                extra_headers=self.connect_headers(),
                ping_interval=None,
                close_timeout=10,
            )
            self.snapshot.connected = True
            self.snapshot.ever_connected = True
            self.snapshot.last_error = ""
            self.snapshot.consecutive_protocol_errors = 0
            self.snapshot.last_message_time = None
            self.reconnect.on_connect_success()
            self.logger.info("[websocket][%s] connected url=%s", self.name, self.url)
            return True
        except Exception as exc:
            self.snapshot.connected = False
            self.snapshot.error_count += 1
            self.snapshot.last_error = f"{type(exc).__name__}: {exc}"
            delay = self.reconnect.on_connect_failure(self.snapshot.last_error)
            self.snapshot.consecutive_failures = self.reconnect.consecutive_failures
            self.snapshot.total_reconnects = self.reconnect.total_reconnects
            self.logger.warning(
                "[websocket][%s] connect_failed consecutive=%s delay=%.1fs error=%s",
                self.name,
                self.snapshot.consecutive_failures,
                delay,
                self.snapshot.last_error,
            )
            return False

    async def disconnect(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            finally:
                self.ws = None
        self.snapshot.connected = False

    async def _receive_loop(self) -> None:
        if self.ws is None:
            return

        async for message in self.ws:
            self.snapshot.message_count += 1
            self.snapshot.last_message_time = self._now()
            try:
                await self.handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.snapshot.error_count += 1
                self.snapshot.last_error = f"{type(exc).__name__}: {exc}"
                self.logger.warning(
                    "[websocket][%s] message_error error=%s",
                    self.name,
                    self.snapshot.last_error,
                )
                raise

    async def _heartbeat_loop(self) -> None:
        if self.heartbeat_interval <= 0:
            return

        while not self._stop_requested:
            await asyncio.sleep(self.heartbeat_interval)
            if self._stop_requested:
                return
            await self.send_heartbeat()
            if self.snapshot.last_message_time is None:
                continue
            elapsed = (self._now() - self.snapshot.last_message_time).total_seconds()
            if elapsed > self.heartbeat_interval + self.heartbeat_timeout:
                raise TimeoutError(
                    f"heartbeat timeout: {elapsed:.0f}s without incoming messages"
                )

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        while not self._stop_requested:
            connected = await self.connect()
            if not connected:
                if not await self.reconnect.wait_before_retry(self._stop_event, self.reconnect.last_delay):
                    break
                continue

            try:
                await self.after_connect()
                receiver = asyncio.create_task(self._receive_loop())
                heartbeat = asyncio.create_task(self._heartbeat_loop())
                done, pending = await asyncio.wait(
                    [receiver, heartbeat],
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
                if not self._stop_requested:
                    raise ConnectionError("websocket connection closed")
            except asyncio.CancelledError:
                break
            except WebSocketException as exc:
                self.snapshot.error_count += 1
                self.snapshot.last_error = f"{type(exc).__name__}: {exc}"
                delay = self.reconnect.on_connect_failure(self.snapshot.last_error)
                self.snapshot.consecutive_failures = self.reconnect.consecutive_failures
                self.snapshot.total_reconnects = self.reconnect.total_reconnects
                self.logger.warning(
                    "[websocket][%s] websocket_exception consecutive=%s delay=%.1fs error=%s",
                    self.name,
                    self.snapshot.consecutive_failures,
                    delay,
                    self.snapshot.last_error,
                )
                if not await self.reconnect.wait_before_retry(self._stop_event, delay):
                    break
            except Exception as exc:
                if self._stop_requested:
                    break
                self.snapshot.error_count += 1
                self.snapshot.last_error = f"{type(exc).__name__}: {exc}"
                delay = self.reconnect.on_connect_failure(self.snapshot.last_error)
                self.snapshot.consecutive_failures = self.reconnect.consecutive_failures
                self.snapshot.total_reconnects = self.reconnect.total_reconnects
                self.logger.warning(
                    "[websocket][%s] run_error consecutive=%s delay=%.1fs error=%s",
                    self.name,
                    self.snapshot.consecutive_failures,
                    delay,
                    self.snapshot.last_error,
                )
                if not await self.reconnect.wait_before_retry(self._stop_event, delay):
                    break
            finally:
                await self.disconnect()

    def request_stop(self) -> None:
        self._stop_requested = True
        self.snapshot.connected = False
        self._stop_event.set()
        if self.ws is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(asyncio.create_task, self.disconnect())

    def get_stats(self) -> Dict:
        self.snapshot.consecutive_failures = self.reconnect.consecutive_failures
        self.snapshot.total_reconnects = self.reconnect.total_reconnects
        return self.snapshot.to_dict()
