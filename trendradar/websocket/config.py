# coding=utf-8
"""
WebSocket 配置加载与兼容处理。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _get_env_bool(key: str) -> Optional[bool]:
    value = os.environ.get(key, "").strip().lower()
    if not value:
        return None
    return value in {"1", "true", "yes", "on"}


def _get_env_int(key: str) -> Optional[int]:
    value = os.environ.get(key, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_env_str(key: str) -> str:
    return os.environ.get(key, "").strip()


def load_websocket_config(
    config_data: Dict[str, Any],
    *,
    config_dir: str = "config",
    default_alert_webhook: str = "",
) -> Dict[str, Any]:
    raw_config = _resolve_raw_websocket_config(config_data, config_dir)
    enabled_env = _get_env_bool("WEBSOCKET_ENABLED")
    alert_webhook_env = _get_env_str("WEBSOCKET_ALERT_WEBHOOK_URL")
    queue_max_size_env = _get_env_int("WEBSOCKET_QUEUE_MAX_SIZE")
    health_log_interval_env = _get_env_int("WEBSOCKET_HEALTH_LOG_INTERVAL_SECONDS")

    channels = raw_config.get("channels", {})
    jin10 = channels.get("jin10", {})
    jin10_reconnect = jin10.get("reconnect", {})
    jin10_protocol = jin10.get("protocol", {})
    logging = raw_config.get("logging", {})
    alerts = raw_config.get("alerts", {})
    processing = raw_config.get("processing", {})
    monitoring = raw_config.get("monitoring", {})

    config = {
        "ENABLED": enabled_env if enabled_env is not None else raw_config.get("enabled", False),
        "QUEUE_MAX_SIZE": queue_max_size_env or processing.get("queue_max_size", 1000),
        "HEALTH_LOG_INTERVAL_SECONDS": health_log_interval_env or monitoring.get("health_log_interval_seconds", 300),
        "HEALTH_CHECK_INTERVAL_SECONDS": monitoring.get("health_check_interval_seconds", 60),
        "LOGGING": {
            "LEVEL": logging.get("level", "INFO"),
            "FILE": logging.get("file", "output/logs/websocket.log"),
            "MAX_SIZE_MB": logging.get("max_size_mb", 10),
            "BACKUP_COUNT": logging.get("backup_count", 5),
        },
        "ALERTS": {
            "ENABLED": alerts.get("enabled", True),
            "FAILURE_THRESHOLD": alerts.get("failure_threshold", 5),
            "OUTAGE_SECONDS": alerts.get("outage_seconds", 600),
            "PROTOCOL_ERROR_THRESHOLD": alerts.get("protocol_error_threshold", 20),
            "QUEUE_BACKLOG_THRESHOLD": alerts.get("queue_backlog_threshold", 100),
            "COOLDOWN_SECONDS": alerts.get("cooldown_seconds", 1800),
            "WEBHOOK_URL": alert_webhook_env or alerts.get("webhook_url", "") or default_alert_webhook,
        },
        "CHANNELS": {
            "jin10": {
                "ENABLED": jin10.get("enabled", False),
                "URL": jin10.get("url", ""),
                "IS_VIP": jin10.get("is_vip", False),
                "HEARTBEAT_INTERVAL": jin10.get("heartbeat_interval", 30),
                "HEARTBEAT_TIMEOUT": jin10.get("heartbeat_timeout", 10),
                "RECONNECT": {
                    "INITIAL_DELAY": jin10_reconnect.get("initial_delay", 1),
                    "MAX_DELAY": jin10_reconnect.get("max_delay", 60),
                    "BACKOFF_FACTOR": jin10_reconnect.get("backoff_factor", 2.0),
                },
                "PROTOCOL": {
                    "ORIGIN": jin10_protocol.get("origin", "https://www.jin10.com"),
                    "USER_AGENT": jin10_protocol.get(
                        "user_agent",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    ),
                },
            }
        },
    }
    return config


def _resolve_raw_websocket_config(config_data: Dict[str, Any], config_dir: str) -> Dict[str, Any]:
    websocket = config_data.get("websocket")
    if isinstance(websocket, dict) and websocket:
        return websocket

    legacy_path = Path(config_dir) / "websocket.yaml"
    if not legacy_path.exists():
        return {}

    with open(legacy_path, "r", encoding="utf-8") as f:
        legacy_config = yaml.safe_load(f) or {}

    if _looks_like_runtime_websocket_config(legacy_config):
        return legacy_config

    return _translate_legacy_websocket_config(legacy_config)


def _looks_like_runtime_websocket_config(raw_config: Dict[str, Any]) -> bool:
    return isinstance(raw_config, dict) and (
        "channels" in raw_config
        or "enabled" in raw_config
        or "alerts" in raw_config
    )


def _translate_legacy_websocket_config(legacy_config: Dict[str, Any]) -> Dict[str, Any]:
    global_config = legacy_config.get("global", {})
    sources = legacy_config.get("sources", {})
    processing = legacy_config.get("processing", {})
    queue_config = processing.get("queue", {})
    logging = legacy_config.get("logging", {})
    monitoring = legacy_config.get("monitoring", {})
    jin10 = sources.get("jin10", {})
    reconnect = jin10.get("reconnect", {})

    return {
        "enabled": global_config.get("enabled", False),
        "processing": {
            "queue_max_size": queue_config.get("max_size", 1000),
        },
        "monitoring": {
            "health_log_interval_seconds": monitoring.get("stats_interval", 300),
            "health_check_interval_seconds": monitoring.get("health_check_interval", 60),
        },
        "logging": logging,
        "channels": {
            "jin10": {
                "enabled": jin10.get("enabled", False),
                "url": jin10.get("url", ""),
                "is_vip": jin10.get("is_vip", False),
                "heartbeat_interval": global_config.get("heartbeat_interval", 30),
                "heartbeat_timeout": global_config.get("heartbeat_timeout", 10),
                "reconnect": {
                    "initial_delay": reconnect.get("initial_delay", 1),
                    "max_delay": reconnect.get("max_delay", global_config.get("max_reconnect_delay", 60)),
                    "backoff_factor": reconnect.get("backoff_factor", 2.0),
                },
            }
        },
        "alerts": {},
    }
