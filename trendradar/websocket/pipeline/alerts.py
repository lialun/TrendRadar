# coding=utf-8
"""
Rate-limited websocket alert manager.
"""

from __future__ import annotations

import time


class WebSocketAlertManager:
    def __init__(self, sender, *, logger, cooldown_seconds: int = 1800, enabled: bool = True):
        self.sender = sender
        self.logger = logger
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled
        self._last_sent = {}
        self._active = set()

    def notify_failure(self, key: str, message: str) -> bool:
        if not self.enabled or self.sender is None or not getattr(self.sender, "enabled", True):
            return False

        now = time.time()
        last_sent = self._last_sent.get(key, 0.0)
        if now - last_sent < self.cooldown_seconds:
            return False

        ok = self.sender.send_text(message)
        if ok:
            self._last_sent[key] = now
            self._active.add(key)
            self.logger.warning("[websocket][alert] failure key=%s", key)
        return ok

    def notify_recovery(self, key: str, message: str) -> bool:
        if key not in self._active:
            return False
        self._active.discard(key)
        ok = self.sender.send_text(message) if self.sender is not None else False
        if ok:
            self.logger.info("[websocket][alert] recovery key=%s", key)
        return ok

    def is_active(self, key: str) -> bool:
        return key in self._active
