# coding=utf-8
"""
Dedicated websocket runtime service entrypoint.
"""

from __future__ import annotations

import signal
import sys
import threading
import time

from trendradar.context import AppContext
from trendradar.core.loader import load_config
from trendradar.websocket.runtime import build_websocket_runtime


def main() -> int:
    config = load_config()
    ctx = AppContext(config)
    stop_event = threading.Event()

    def _signal_handler(signum, frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    runtime = None
    try:
        proxy_url = config.get("DEFAULT_PROXY") if config.get("USE_PROXY") else None
        dedup_service = ctx.create_dedup_service()
        runtime = build_websocket_runtime(
            ctx,
            dedup_service,
            proxy_url=proxy_url,
        )
        if runtime is None:
            print("[WebSocket] 未启用，退出")
            return 1

        if not runtime.start():
            print("[WebSocket] 启动失败，退出")
            return 1

        print("[WebSocket] 常驻服务已启动")
        while not stop_event.is_set():
            time.sleep(1)
        return 0
    finally:
        if runtime is not None:
            runtime.stop()
        ctx.cleanup()


if __name__ == "__main__":
    sys.exit(main())
