# coding=utf-8
"""
Reconnect strategy for websocket channels.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional


class ReconnectController:
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.current_delay = initial_delay
        self.last_delay = initial_delay
        self.consecutive_failures = 0
        self.total_reconnects = 0
        self.last_success_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.last_failure_reason: str = ""

    def on_connect_success(self) -> None:
        self.current_delay = self.initial_delay
        self.last_delay = self.initial_delay
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.last_failure_reason = ""

    def on_connect_failure(self, reason: str) -> float:
        delay = self.current_delay
        self.last_delay = delay
        self.consecutive_failures += 1
        self.total_reconnects += 1
        self.last_failure_time = datetime.now()
        self.last_failure_reason = reason
        self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)
        return delay

    async def wait_before_retry(self, stop_event: asyncio.Event, delay: float) -> bool:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return False
        except asyncio.TimeoutError:
            return True
