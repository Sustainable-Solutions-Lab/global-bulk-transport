"""Per-tonne handling cost & CO2 at transshipment edges."""
from __future__ import annotations

from global_bulk_transport.config import transshipment_config

# Transshipment kinds emitted by network/transshipment_build.py:
# road_to_rail, road_to_inland, road_to_sea, rail_to_inland, rail_to_sea,
# inland_to_sea. We also accept the symmetric forms (rail_to_road etc.)
# transparently because the underlying physical operation is the same.
_REVERSE = {
    "rail_to_road":   "road_to_rail",
    "inland_to_road": "road_to_inland",
    "sea_to_road":    "road_to_sea",
    "inland_to_rail": "rail_to_inland",
    "sea_to_rail":    "rail_to_sea",
    "sea_to_inland":  "inland_to_sea",
}


def _canonical(kind: str) -> str:
    return _REVERSE.get(kind, kind)


def handling(kind: str, iso: str | None) -> tuple[float, float]:
    """Return (cost_usd_per_t, co2_kg_per_t) for a transshipment kind.

    Country factor resolution mirrors lookup._country_factor:
    yaml override -> LPI-derived `handling_cost_factor` -> default.
    """
    cfg = transshipment_config()
    k = _canonical(kind)
    cost = cfg["cost_usd_per_t"][k]
    co2  = cfg["co2_kg_per_t"][k]
    table = cfg["country_factor"]
    if iso is not None and iso in table["countries"]:
        factor = float(table["countries"][iso])
    else:
        from global_bulk_transport.attributes.lookup import _lpi_table
        lpi = _lpi_table()
        if lpi is not None and iso is not None and iso in lpi.index:
            factor = float(lpi.loc[iso, "handling_cost_factor"])
        else:
            factor = float(table["default"])
    return float(cost) * factor, float(co2)
