# coding=utf-8
"""
通知去重配置
"""

import os
from typing import Any, Dict


def _get_env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _get_env_int(key: str, default: int) -> int:
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_str(key: str, default: str) -> str:
    return os.environ.get(key, "").strip() or default


def load_dedup_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    notification = config_data.get("notification", {})
    dedup = notification.get("dedup", {})
    model_paths = dedup.get("model_paths", {})

    enabled = _get_env_bool("DEDUP_ENABLED", dedup.get("enabled", False))
    window_hours = _get_env_int("DEDUP_WINDOW_HOURS", dedup.get("window_hours", 72))
    top_k = _get_env_int("DEDUP_TOP_K", dedup.get("top_k", 20))
    rerank_threshold = _get_env_float(
        "DEDUP_RERANK_THRESHOLD", dedup.get("rerank_threshold", 0.82)
    )
    strict_time_conflict = _get_env_bool(
        "DEDUP_STRICT_TIME_CONFLICT", dedup.get("strict_time_conflict", True)
    )

    return {
        "ENABLED": enabled,
        "WINDOW_HOURS": max(1, window_hours),
        "TOP_K": max(1, top_k),
        "RERANK_THRESHOLD": max(0.0, min(1.0, rerank_threshold)),
        "STRICT_TIME_CONFLICT": strict_time_conflict,
        "EMBED_MODEL_PATH": _get_env_str(
            "DEDUP_EMBED_MODEL_PATH", model_paths.get("embed", "/models/dedup-embed")
        ),
        "RERANK_MODEL_PATH": _get_env_str(
            "DEDUP_RERANK_MODEL_PATH", model_paths.get("rerank", "/models/dedup-rerank")
        ),
    }
