"""Project-wide config loading.

All numerical assumptions live in YAML/GeoJSON under ``config/`` and are
loaded once from here. Code never hard-codes cost or CO2 numbers.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@lru_cache(maxsize=1)
def project_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "config.yaml").read_text())


@lru_cache(maxsize=1)
def cost_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "cost.yaml").read_text())


@lru_cache(maxsize=1)
def co2_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "co2.yaml").read_text())


@lru_cache(maxsize=1)
def transshipment_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "transshipment.yaml").read_text())


def path(key: str) -> Path:
    """Resolve a configured path relative to project root."""
    return ROOT / project_config()["paths"][key]
