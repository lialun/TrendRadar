# coding=utf-8
"""
WebSocket runtime logging helpers.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict


def setup_websocket_logger(config: Dict) -> logging.Logger:
    logger = logging.getLogger("trendradar.websocket")
    if getattr(logger, "_trendradar_websocket_configured", False):
        return logger

    logging_config = config.get("LOGGING", {})
    level_name = str(logging_config.get("LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_path = logging_config.get("FILE", "output/logs/websocket.log")
    if file_path:
        log_path = Path(file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=int(logging_config.get("MAX_SIZE_MB", 10) * 1024 * 1024),
            backupCount=int(logging_config.get("BACKUP_COUNT", 5)),
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger._trendradar_websocket_configured = True
    return logger
