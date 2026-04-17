# coding=utf-8
"""
Compact Feishu sender for websocket realtime events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests

from trendradar.core.config import limit_accounts, parse_multi_account_config
from trendradar.websocket.models import RealtimeEvent


JIN10_MESSAGE_TYPE_MAP = {
    1000: "",
    1001: "事件快讯",
    1002: "语音消息",
    1100: "VIP快讯",
    1110: "VIP重要快讯",
}


class RealtimeFeishuSender:
    def __init__(
        self,
        webhook_config: str,
        *,
        logger,
        max_accounts: int = 3,
        proxy_url: Optional[str] = None,
        label: str = "websocket",
    ):
        self.webhook_config = webhook_config
        self.logger = logger
        self.max_accounts = max_accounts
        self.proxy_url = proxy_url
        self.label = label

    @property
    def enabled(self) -> bool:
        return bool(self._account_urls())

    @property
    def target_count(self) -> int:
        return len(self._account_urls())

    def _account_urls(self) -> list[str]:
        accounts = parse_multi_account_config(self.webhook_config)
        accounts = [item for item in accounts if item]
        return limit_accounts(accounts, self.max_accounts, f"{self.label}-feishu")

    def send_event(self, event: RealtimeEvent) -> bool:
        return self.send_text(self.render_event(event))

    def send_text(self, content: str, webhook_override: Optional[str] = None) -> bool:
        targets = [webhook_override] if webhook_override else self._account_urls()
        if not targets:
            self.logger.info("[websocket][feishu] no webhook configured for %s", self.label)
            return False

        success_count = 0
        for url in targets:
            if self._send_one(url, content):
                success_count += 1

        if 0 < success_count < len(targets):
            self.logger.warning(
                "[websocket][feishu] partial_success label=%s success=%s total=%s",
                self.label,
                success_count,
                len(targets),
            )

        return success_count > 0

    def render_event(self, event: RealtimeEvent) -> str:
        title = (event.title or "").strip()
        content = (event.content or "").strip()
        vip_title = str(event.meta.get("vip_title", "") or "").strip()
        msg_id = int(event.meta.get("msg_id", 0) or 0)
        channel_label = "金十数据" if event.channel == "jin10" else event.channel
        type_label = JIN10_MESSAGE_TYPE_MAP.get(msg_id, "")
        event_title = title or vip_title or _extract_title_from_content(content)
        event_content = _strip_embedded_title(content)
        display_text = event_title or event_content or "(无内容)"
        time_display = _format_time(event.published_at)

        first_line = f"[{channel_label}]"
        if type_label:
            first_line += f"[{type_label}]"

        if event.detail_url and event_title:
            first_line += f"[{event_title}]({event.detail_url})"
        else:
            first_line += display_text

        first_line += f" <font color='grey'>- {time_display}</font>"
        if event_title and event_content:
            return f"{first_line}\n{event_content}"
        if event.detail_url and display_text:
            return f"[{channel_label}]{f'[{type_label}]' if type_label else ''}[{display_text}]({event.detail_url}) <font color='grey'>- {time_display}</font>"
        return first_line

    def _send_one(self, webhook_url: str, content: str) -> bool:
        headers = {"Content-Type": "application/json"}
        proxies = None
        if self.proxy_url:
            proxies = {"http": self.proxy_url, "https": self.proxy_url}

        if "www.feishu.cn" in webhook_url:
            payload = {"msg_type": "text", "content": {"text": content}}
        else:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "schema": "2.0",
                    "body": {"elements": [{"tag": "markdown", "content": content}]},
                },
            }

        try:
            response = requests.post(
                webhook_url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=10,
            )
            if response.status_code != 200:
                self.logger.warning(
                    "[websocket][feishu] http_error status=%s label=%s",
                    response.status_code,
                    self.label,
                )
                return False

            result = response.json()
            if result.get("StatusCode") == 0 or result.get("code") == 0:
                return True

            error_msg = result.get("msg") or result.get("StatusMessage", "unknown error")
            self.logger.warning(
                "[websocket][feishu] api_error label=%s error=%s",
                self.label,
                error_msg,
            )
            return False
        except Exception as exc:
            self.logger.warning(
                "[websocket][feishu] send_error label=%s error=%s:%s",
                self.label,
                type(exc).__name__,
                exc,
            )
            return False


def _format_time(value: str) -> str:
    if not value:
        return datetime.now().strftime("%H:%M")
    if " " in value:
        return value.split(" ", 1)[1][:5]
    return value[:5]


def _extract_title_from_content(content: str) -> str:
    if content.startswith("【") and "】" in content:
        return content[1:content.index("】")].strip()
    return ""


def _strip_embedded_title(content: str) -> str:
    if content.startswith("【") and "】" in content:
        return content[content.index("】") + 1 :].strip()
    return content
