"""Per-edge cost & CO2 unit lookups for road / rail / inland-waterway.

The selection logic is:

    road:    base USD/tkm (cost.yaml#defaults.road_truck_bulk)
             * road_country_factor[iso] (default 1.0)
    rail:    base USD/tkm (cost.yaml#defaults.rail_unit_train)
             * rail_country_factor[iso]
    barge:   base USD/tkm (cost.yaml#defaults.inland_barge)
             * barge_country_factor[iso]
             [class adjustment built into co2 only — cost is already
              tonnage-normalised]

CO2 mirrors the same structure but selects per-CEMT-class for inland
barge and applies a per-country grid factor to electric rail.
"""
from __future__ import annotations

from global_bulk_transport.config import co2_config, cost_config


def _country_factor(table: dict, iso: str | None) -> float:
    return float(table["countries"].get(iso, table["default"]))


def edge_cost_usd_per_tkm(mode: str, iso: str | None, edge_attrs) -> float:
    cfg = cost_config()
    if mode == "road":
        base = cfg["defaults"]["road_truck_bulk"]
        return base * _country_factor(cfg["road_country_factor"], iso)
    if mode == "rail":
        base = cfg["defaults"]["rail_unit_train"]
        return base * _country_factor(cfg["rail_country_factor"], iso)
    if mode == "inland_waterway":
        base = cfg["defaults"]["inland_barge"]
        return base * _country_factor(cfg["barge_country_factor"], iso)
    raise ValueError(f"non-line-haul mode passed to edge_cost_usd_per_tkm: {mode}")


def edge_co2_g_per_tkm(mode: str, iso: str | None, edge_attrs) -> float:
    cfg = co2_config()
    if mode == "road":
        base = cfg["defaults"]["road_truck_bulk"]
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
