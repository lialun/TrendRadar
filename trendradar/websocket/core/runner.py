# coding=utf-8
"""
Threaded asyncio loop runner.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable, Optional


class AsyncLoopThread:
    def __init__(self, logger):
        self.logger = logger
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def start(self, coroutine_factory: Callable[[], Awaitable[None]]) -> None:
        if self.thread and self.thread.is_alive():
            return

        def _target() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._ready.set()
            try:
                self.loop.run_until_complete(coroutine_factory())
            finally:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self.loop.close()
                self.loop = None

        self.thread = threading.Thread(target=_target, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=5)

    def call_soon(self, func, *args) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(func, *args)

    def join(self, timeout: float = 10.0) -> None:
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
