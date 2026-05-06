"""Per-edge cost & CO2 unit lookups for road / rail / inland-waterway.

Country adjustment resolution order, highest priority first:
  1. LPI-derived factor (config/lpi_country_factors.csv) — auto-built by
     ``network/fetch_lpi.py`` from World Bank LPI 2023 + 2018 fallback.
  2. Hand-set factor in cost.yaml#road_country_factor.countries[iso]
     (overrides for countries where domain knowledge differs from LPI).
  3. cost.yaml#road_country_factor.default.

CO2 mirrors the same structure but selects per-CEMT-class for inland
barge and applies a per-country grid factor to electric rail.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from global_bulk_transport.config import CONFIG_DIR, co2_config, cost_config


@lru_cache(maxsize=1)
def _lpi_table() -> pd.DataFrame | None:
    p = Path(CONFIG_DIR) / "lpi_country_factors.csv"
    if not p.exists():
        return None
    return pd.read_csv(p).set_index("iso_a2")


def _country_factor(table: dict, iso: str | None, lpi_col: str | None = None) -> float:
    """Resolve country factor. Hand-set yaml takes precedence over LPI to
    let domain overrides win for known special cases. LPI applies for the
    long tail."""
    if iso is not None and iso in table["countries"]:
        return float(table["countries"][iso])
    if lpi_col is not None and iso is not None:
        lpi = _lpi_table()
        if lpi is not None and iso in lpi.index:
            return float(lpi.loc[iso, lpi_col])
    return float(table["default"])


def edge_cost_usd_per_tkm(mode: str, iso: str | None, edge_attrs) -> float:
    cfg = cost_config()
    if mode == "road":
        base = cfg["defaults"]["road_truck_bulk"]
        return base * _country_factor(cfg["road_country_factor"], iso, "road_cost_factor")
    if mode == "rail":
        base = cfg["defaults"]["rail_unit_train"]
        return base * _country_factor(cfg["rail_country_factor"], iso, "rail_cost_factor")
    if mode == "inland_waterway":
        base = cfg["defaults"]["inland_barge"]
        return base * _country_factor(cfg["barge_country_factor"], iso, "barge_cost_factor")
    raise ValueError(f"non-line-haul mode passed to edge_cost_usd_per_tkm: {mode}")


def edge_co2_g_per_tkm(mode: str, iso: str | None, edge_attrs) -> float:
    cfg = co2_config()
    if mode == "road":
        base = cfg["defaults"]["road_truck_bulk"]
        # CO2 country factor is fleet-/fuel-quality based — keep yaml-only
        return base * _country_factor(cfg["road_country_factor"], iso)

    if mode == "rail":
        electrified = bool(edge_attrs["electrified"]) if edge_attrs["electrified"] is not None else False
        if not electrified:
            return float(cfg["defaults"]["rail_diesel"])
        grid = cfg["electric_rail_grid_g_per_kwh"]
        intensity = grid["energy_intensity_kwh_per_tkm"]
        g_per_kwh = grid["countries"].get(iso, None)
        if g_per_kwh is None:
            return float(cfg["defaults"]["rail_electric"])
        return float(g_per_kwh) * float(intensity)

    if mode == "inland_waterway":
        cls = edge_attrs["cemt_class"]
        if cls == "I":
            return float(cfg["defaults"]["inland_barge_class_I"])
        if cls == "IV":
            return float(cfg["defaults"]["inland_barge_class_IV"])
        if cls in ("VIa", "VIb", "VIc", "VII"):
            return float(cfg["defaults"]["inland_barge_class_VI"])
        return float(cfg["defaults"]["inland_barge"])

    raise ValueError(f"non-line-haul mode passed to edge_co2_g_per_tkm: {mode}")
