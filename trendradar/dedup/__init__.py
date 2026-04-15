# coding=utf-8
"""
本地通知去重模块
"""

from .config import load_dedup_config
from .service import DedupService

__all__ = ["load_dedup_config", "DedupService"]
