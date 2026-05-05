"""Build rail edges GeoPackage from Natural Earth 10m railroads.

Schema:
    geometry, mode='rail', length_km, iso_a2, electrified (bool, best-effort)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd

from global_bulk_transport.geometry import line_length_km
from global_bulk_transport.logging_setup import get_logger
from global_bulk_transport.network.countries import tag_country
from global_bulk_transport.network.io import fetch_ne_layer

log = get_logger(__name__)

# Country-level electrification ratio (UIC 2022 figures, network-km share).
# This is used as a probabilistic 'is_electrified' proxy when NE has no
# attribute. Country average is fine for our SSSP fidelity.
ELECTRIFICATION_FRACTION = {
    "CH": 1.00, "NL": 0.95, "BE": 0.90, "SE": 0.74, "NO": 0.55,
    "ES": 0.65, "IT": 0.71, "FR": 0.55, "DE": 0.55, "AT": 0.74,
    "GB": 0.42, "PL": 0.65, "CZ": 0.34, "JP": 0.66, "KR": 0.78,
    "CN": 0.74, "IN": 0.85, "RU": 0.51, "TR": 0.45, "ZA": 0.40,
    "US": 0.01, "CA": 0.01, "AU": 0.07, "BR": 0.08, "AR": 0.05,
    "MX": 0.02, "EG": 0.10,
}


def build(out: Path) -> None:
    shp = fetch_ne_layer("railroads")
    log.info("reading %s", shp)
    gdf = gpd.read_file(shp)
    gdf["mode"] = "rail"
    gdf["from_mode"] = "rail"
    gdf["to_mode"] = "rail"
    gdf["length_km"] = gdf.geometry.apply(line_length_km)
    gdf = gdf[gdf["length_km"] > 0].copy()
    gdf = tag_country(gdf)
    gdf["electrified"] = gdf["iso_a2"].map(
        lambda c: ELECTRIFICATION_FRACTION.get(c, 0.10) >= 0.5
    )

    keep = ["mode", "from_mode", "to_mode", "length_km", "iso_a2", "electrified", "geometry"]
    gdf = gdf[keep]

    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    log.info("wrote %d rail edges -> %s", len(gdf), out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
