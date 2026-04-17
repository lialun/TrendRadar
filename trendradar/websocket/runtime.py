# coding=utf-8
"""
Main-process websocket runtime.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

from trendradar.websocket.channels.jin10 import Jin10Channel
from trendradar.websocket.core.runner import AsyncLoopThread
from trendradar.websocket.logging import setup_websocket_logger
from trendradar.websocket.models import RealtimeEvent
from trendradar.websocket.pipeline.alerts import WebSocketAlertManager
from trendradar.websocket.pipeline.dedup import RealtimeDedupAdapter
from trendradar.websocket.pipeline.feishu import RealtimeFeishuSender


def _serialize_log_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list, tuple)):
        if not value:
            return "{}" if isinstance(value, dict) else "[]"
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    text = str(value).strip()
    if not text:
        return "-"
    return text


def _format_log_field(name: str, value) -> str:
    rendered = _serialize_log_value(value).replace("\r\n", "\n").replace("\r", "\n")
    return f"  {name}={rendered.replace('\n', '\n    ')}"


def _preview_text(value: str, limit: int = 80) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)]}..."


def _build_duplicate_log(event: RealtimeEvent, candidate, duplicate: Dict[str, object]) -> str:
    lines = [
        (
            "[websocket][pipeline] duplicate channel="
            f"{event.channel} dedup_key={event.dedup_key or '-'} "
            f"reason={duplicate.get('reason', 'unknown')} scope={duplicate.get('scope', '-')}"
        ),
        _format_log_field("event_type", event.event_type),
        _format_log_field("source_message_id", event.source_message_id),
        _format_log_field("published_at", event.published_at),
        _format_log_field("detail_url", event.detail_url),
        _format_log_field("meta", event.meta),
        _format_log_field("title", event.title),
        _format_log_field("content", event.content),
        _format_log_field("dedup_text", candidate.title),
        _format_log_field("normalized_title", candidate.normalized_title),
        _format_log_field("fact_signature", candidate.fact_signature),
        _format_log_field("matched_title", duplicate.get("matched_title", "")),
        _format_log_field("matched_region", duplicate.get("matched_region", "")),
        _format_log_field("matched_platform_id", duplicate.get("matched_platform_id", "")),
        _format_log_field("matched_dedup_key", duplicate.get("matched_dedup_key", "")),
        _format_log_field("matched_url", duplicate.get("matched_url", "")),
        _format_log_field("matched_normalized_title", duplicate.get("matched_normalized_title", "")),
        _format_log_field("matched_fact_signature", duplicate.get("matched_fact_signature", {})),
    ]
    if "score" in duplicate:
        lines.append(_format_log_field("score", duplicate.get("score")))
    return "\n".join(lines)


def _build_send_failed_log(event: RealtimeEvent, candidate, sender: RealtimeFeishuSender) -> str:
    lines = [
        (
            "[websocket][pipeline] send_failed channel="
            f"{event.channel} dedup_key={event.dedup_key or '-'} "
            f"sender_label={sender.label}"
        ),
        _format_log_field("event_type", event.event_type),
        _format_log_field("source_message_id", event.source_message_id),
        _format_log_field("published_at", event.published_at),
        _format_log_field("detail_url", event.detail_url),
        _format_log_field("sender_enabled", sender.enabled),
        _format_log_field("sender_targets", sender.target_count),
        _format_log_field("meta", event.meta),
        _format_log_field("title", event.title),
        _format_log_field("content", event.content),
        _format_log_field("dedup_text", candidate.title),
        _format_log_field("normalized_title", candidate.normalized_title),
        _format_log_field("fact_signature", candidate.fact_signature),
    ]
    return "\n".join(lines)


def _build_sent_log(event: RealtimeEvent, candidate) -> str:
    return (
        "[websocket][pipeline] sent channel="
        f"{event.channel} dedup_key={event.dedup_key or '-'} "
        f"summary={_preview_text(candidate.title)}"
    )


class RealtimePipeline:
    def __init__(
        self,
        *,
        dedup_adapter: RealtimeDedupAdapter,
        feishu_sender: RealtimeFeishuSender,
        logger,
        now_func: Callable[[], datetime],
        event_callback: Optional[Callable[[RealtimeEvent], None]] = None,
    ):
        self.dedup_adapter = dedup_adapter
        self.feishu_sender = feishu_sender
        self.logger = logger
        self.now_func = now_func
        self.event_callback = event_callback
        self.stats = {
            "total_received": 0,
            "filtered_duplicate": 0,
            "sent_success": 0,
            "sent_failed": 0,
        }

    def process_event(self, event: RealtimeEvent) -> bool:
        self.stats["total_received"] += 1
        if self.event_callback:
            self.event_callback(event)

        now = self.now_func()
        candidate, duplicate = self.dedup_adapter.check(event, now)
        if duplicate:
            self.stats["filtered_duplicate"] += 1
            self.logger.info(_build_duplicate_log(event, candidate, duplicate))
            return False

        sent = self.feishu_sender.send_event(event)
        if not sent:
            self.stats["sent_failed"] += 1
            self.logger.warning(_build_send_failed_log(event, candidate, self.feishu_sender))
            return False

        self.dedup_adapter.record_sent(candidate, now)
        self.stats["sent_success"] += 1
        self.logger.info(_build_sent_log(event, candidate))
        return True


class WebSocketRuntime:
    def __init__(
        self,
        *,
        config: Dict,
        dedup_service,
        feishu_webhook: str,
        max_accounts: int,
        now_func: Callable[[], datetime],
        proxy_url: Optional[str] = None,
        event_callback: Optional[Callable[[RealtimeEvent], None]] = None,
    ):
        self.config = config
        self.logger = setup_websocket_logger(config)
        self.now_func = now_func
        self.proxy_url = proxy_url
        self.event_queue: queue.Queue[RealtimeEvent] = queue.Queue(
            maxsize=int(config.get("QUEUE_MAX_SIZE", 1000))
        )
        self.loop_runner = AsyncLoopThread(self.logger)
        self._async_stop_event = None
        self._stop_event = threading.Event()
        self._consumer_thread: Optional[threading.Thread] = None
        self._running = False
        self._start_time: Optional[datetime] = None
        self.channels = {}
        self.queue_dropped = 0

        self.feishu_sender = RealtimeFeishuSender(
            feishu_webhook,
            logger=self.logger,
            max_accounts=max_accounts,
            proxy_url=proxy_url,
            label="news",
        )
        alerts_config = config.get("ALERTS", {})
        self.alert_sender = RealtimeFeishuSender(
            alerts_config.get("WEBHOOK_URL", ""),
            logger=self.logger,
            max_accounts=max_accounts,
            proxy_url=proxy_url,
            label="alerts",
        )
        self.alert_manager = WebSocketAlertManager(
            self.alert_sender,
            logger=self.logger,
            cooldown_seconds=int(alerts_config.get("COOLDOWN_SECONDS", 1800)),
            enabled=bool(alerts_config.get("ENABLED", True)),
        )
        self.pipeline = RealtimePipeline(
            dedup_adapter=RealtimeDedupAdapter(dedup_service),
            feishu_sender=self.feishu_sender,
            logger=self.logger,
            now_func=now_func,
            event_callback=event_callback,
        )

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return True
        if not self.config.get("ENABLED", False):
            return False

        self._build_channels()
        if not self.channels:
            self.logger.warning("[websocket][runtime] no enabled channel configured")
            return False

        self._running = True
        self._start_time = self.now_func()
        self._stop_event.clear()
        self._consumer_thread = threading.Thread(target=self._consumer_loop, daemon=True)
        self._consumer_thread.start()
        self.loop_runner.start(self._async_main)
        self.logger.info("[websocket][runtime] started channels=%s", ",".join(self.channels.keys()))
        return True

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        for channel in self.channels.values():
            channel.request_stop()
        if self._async_stop_event is not None:
            self.loop_runner.call_soon(self._async_stop_event.set)
        self.loop_runner.join(timeout=10)
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=10)
        self.logger.info("[websocket][runtime] stopped")

    def enqueue_event(self, event: RealtimeEvent) -> None:
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            self.queue_dropped += 1
            self.logger.warning(
                "[websocket][runtime] queue_full dropped=%s channel=%s dedup_key=%s",
                self.queue_dropped,
                event.channel,
                event.dedup_key or "-",
            )

    def _build_channels(self) -> None:
        self.channels = {}
        jin10_config = self.config.get("CHANNELS", {}).get("jin10", {})
        if jin10_config.get("ENABLED") and jin10_config.get("URL"):
            self.channels["jin10"] = Jin10Channel(
                jin10_config,
                logger=self.logger,
                event_callback=self.enqueue_event,
            )

    async def _async_main(self) -> None:
        self._async_stop_event = asyncio.Event()
        tasks = [asyncio.create_task(channel.run()) for channel in self.channels.values()]
        await self._async_stop_event.wait()
        for channel in self.channels.values():
            channel.request_stop()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _consumer_loop(self) -> None:
        health_interval = int(self.config.get("HEALTH_LOG_INTERVAL_SECONDS", 300))
        next_health = time.time() + max(1, health_interval)
        while self._running or not self.event_queue.empty():
            try:
                event = self.event_queue.get(timeout=1)
                self.pipeline.process_event(event)
                self.event_queue.task_done()
            except queue.Empty:
                pass
            except Exception as exc:
                self.logger.exception("[websocket][runtime] consumer_error error=%s", exc)

            now_ts = time.time()
            if now_ts >= next_health:
                try:
                    self._log_health_snapshot()
                    self._evaluate_alerts()
                except Exception as exc:
                    self.logger.exception("[websocket][runtime] health_check_error error=%s", exc)
                next_health = now_ts + max(1, health_interval)

    def _log_health_snapshot(self) -> None:
        stats = self.get_stats()
        self.logger.info(
            "[websocket][health] queue=%s dropped=%s sent=%s dup=%s channels=%s",
            stats["queue_size"],
            stats["queue_dropped"],
            stats["pipeline"]["sent_success"],
            stats["pipeline"]["filtered_duplicate"],
            ",".join(
                f"{name}:connected={item['connected']},news={item['news_count']},reconnects={item['total_reconnects']}"
                for name, item in stats["channels"].items()
            ),
        )

    def _evaluate_alerts(self) -> None:
        alerts_config = self.config.get("ALERTS", {})
        failure_threshold = int(alerts_config.get("FAILURE_THRESHOLD", 5))
        outage_seconds = int(alerts_config.get("OUTAGE_SECONDS", 600))
        protocol_error_threshold = int(alerts_config.get("PROTOCOL_ERROR_THRESHOLD", 20))
        queue_backlog_threshold = int(alerts_config.get("QUEUE_BACKLOG_THRESHOLD", 100))
        now = self.now_func()

        for name, stats in self.get_stats()["channels"].items():
            reconnect_key = f"{name}:reconnect"
            if stats["consecutive_failures"] >= failure_threshold:
                self.alert_manager.notify_failure(
                    reconnect_key,
                    f"[WebSocket告警] 渠道 {name} 连续重连失败 {stats['consecutive_failures']} 次，最近错误：{stats['last_error'] or '未知'}",
                )
            else:
                self.alert_manager.notify_recovery(
                    reconnect_key,
                    f"[WebSocket恢复] 渠道 {name} 重连已恢复。",
                )

            outage_key = f"{name}:outage"
            last_message = stats.get("last_message_time")
            if stats["ever_connected"] and last_message:
                last_dt = self._parse_snapshot_time(last_message, now)
                age = (now - last_dt).total_seconds()
                if age >= outage_seconds and not stats["connected"]:
                    self.alert_manager.notify_failure(
                        outage_key,
                        f"[WebSocket告警] 渠道 {name} 已断连 {int(age)} 秒，最近错误：{stats['last_error'] or '未知'}",
                    )
                else:
                    self.alert_manager.notify_recovery(
                        outage_key,
                        f"[WebSocket恢复] 渠道 {name} 已恢复消息接收。",
                    )

            protocol_key = f"{name}:protocol"
            if stats["consecutive_protocol_errors"] >= protocol_error_threshold:
                self.alert_manager.notify_failure(
                    protocol_key,
                    f"[WebSocket告警] 渠道 {name} 连续协议错误 {stats['consecutive_protocol_errors']} 次，最近错误：{stats['last_error'] or '未知'}",
                )
            else:
                self.alert_manager.notify_recovery(
                    protocol_key,
                    f"[WebSocket恢复] 渠道 {name} 协议错误已恢复。",
                )

        backlog_key = "runtime:queue_backlog"
        queue_size = self.event_queue.qsize()
        if queue_size >= queue_backlog_threshold:
            self.alert_manager.notify_failure(
                backlog_key,
                f"[WebSocket告警] 实时消息队列积压 {queue_size} 条，请检查 websocket pipeline。",
            )
        else:
            self.alert_manager.notify_recovery(
                backlog_key,
                "[WebSocket恢复] 实时消息队列积压已恢复正常。",
            )

    def get_stats(self) -> Dict:
        uptime = None
        if self._start_time is not None:
            uptime = (self.now_func() - self._start_time).total_seconds()
        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "queue_size": self.event_queue.qsize(),
            "queue_dropped": self.queue_dropped,
            "pipeline": dict(self.pipeline.stats),
            "channels": {
                name: channel.get_stats()
                for name, channel in self.channels.items()
            },
        }

    def print_stats(self) -> None:
        stats = self.get_stats()
        self.logger.info("[websocket][stats] %s", stats)

    @staticmethod
    def _parse_snapshot_time(raw_value: str, now: datetime) -> datetime:
        dt = datetime.fromisoformat(raw_value)
        if dt.tzinfo is None and now.tzinfo is not None:
            return dt.replace(tzinfo=now.tzinfo)
        return dt


def build_websocket_runtime(ctx, dedup_service, *, proxy_url: Optional[str] = None, event_callback=None):
    config = ctx.config.get("WEBSOCKET", {})
    if not config.get("ENABLED", False):
        return None

    return WebSocketRuntime(
        config=config,
        dedup_service=dedup_service,
        feishu_webhook=ctx.config.get("FEISHU_WEBHOOK_URL", ""),
        max_accounts=int(ctx.config.get("MAX_ACCOUNTS_PER_CHANNEL", 3)),
        now_func=ctx.get_time,
        proxy_url=proxy_url,
        event_callback=event_callback,
    )
