# coding=utf-8
"""
WebSocket runtime shared models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RealtimeEvent:
    channel: str
    event_type: str
    source_message_id: str = ""
    dedup_key: str = ""
    title: str = ""
    content: str = ""
    published_at: str = ""
    detail_url: str = ""
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_text(self) -> str:
        return (self.content or self.title or "").strip()


@dataclass
class ChannelSnapshot:
    name: str
    connected: bool = False
    ever_connected: bool = False
    message_count: int = 0
    news_count: int = 0
    heartbeat_count: int = 0
    error_count: int = 0
    protocol_error_count: int = 0
    consecutive_protocol_errors: int = 0
    consecutive_failures: int = 0
    total_reconnects: int = 0
    last_message_time: Optional[datetime] = None
    last_error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "ever_connected": self.ever_connected,
            "message_count": self.message_count,
            "news_count": self.news_count,
            "heartbeat_count": self.heartbeat_count,
            "error_count": self.error_count,
            "protocol_error_count": self.protocol_error_count,
            "consecutive_protocol_errors": self.consecutive_protocol_errors,
            "consecutive_failures": self.consecutive_failures,
            "total_reconnects": self.total_reconnects,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "last_error": self.last_error,
            "extra": dict(self.extra),
        }
