# coding=utf-8
"""
Realtime channel interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class RealtimeChannel(ABC):
    name: str

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def request_stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_stats(self) -> Dict:
        raise NotImplementedError
