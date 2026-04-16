# coding=utf-8
"""
Testing helpers for websocket runtime entrypoints.
"""

from __future__ import annotations

from typing import Callable, Tuple

from trendradar.context import AppContext
from trendradar.websocket.runtime import build_websocket_runtime


def build_jin10_test_runtime(config, *, event_callback=None) -> Tuple[object, Callable[[], None]]:
    ctx = AppContext(config)
    dedup_service = ctx.create_dedup_service()
    runtime = build_websocket_runtime(
        ctx,
        dedup_service,
        proxy_url=config.get("DEFAULT_PROXY") if config.get("USE_PROXY") else None,
        event_callback=event_callback,
    )
    if runtime is None:
        raise RuntimeError("websocket runtime is disabled in current config")
    return runtime, runtime.print_stats
