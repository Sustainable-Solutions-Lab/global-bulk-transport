"""Tiny logging helper to keep CLI scripts consistent."""
from __future__ import annotations

import logging
import os


def get_logger(name: str) -> logging.Logger:
    level = os.environ.get("GBT_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )
    return logging.getLogger(name)
