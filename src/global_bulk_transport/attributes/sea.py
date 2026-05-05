"""Maritime per-leg cost & CO2 — vessel class chosen by leg distance.

Logic: short ports legs (<1500 km) use handysize / short-sea factors;
medium legs (1500–6000 km) use supramax/panamax; long legs (>6000 km)
use capesize. This is a coarse heuristic — see methodology.md §3.1.
"""
from __future__ import annotations

from global_bulk_transport.config import co2_config, cost_config


def _bracket(km: float) -> str:
    if km < 1500:
        return "handysize"
    if km < 6000:
        return "supramax" if km < 3500 else "panamax"
    return "capesize"


def sea_cost_co2(length_km: float) -> tuple[float, float]:
    """Return (USD/tkm, g CO2/tkm) for a maritime leg of given length."""
    cls = _bracket(length_km)
    cost = cost_config()["defaults"][f"sea_{cls}"]
    co2 = co2_config()["defaults"][f"sea_{cls}"]
    return float(cost), float(co2)
