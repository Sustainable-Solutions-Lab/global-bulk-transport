"""Build the road edges GeoPackage from Natural Earth 10m roads.

Schema produced (consistent across modes):
    geometry, mode='road', length_km, iso_a2, road_class, speed_kph
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

# Natural Earth road class -> generic class + default speed (km/h)
# Speeds are gap-fill defaults used by attributes/cost.py if a row has no
# OSM-derived maxspeed. Conservative bulk-truck-relevant values.
ROAD_CLASS_MAP = {
    "Major Highway":  ("primary",   90),
    "Secondary Highway": ("secondary", 70),
    "Road":           ("tertiary",  50),
    "Track":          ("track",     30),
    "Ferry Route":    ("ferry",     20),
    "Beltway":        ("primary",   80),
    "Bypass":         ("primary",   80),
    "Unknown":        ("tertiary",  50),
}


def build(out: Path) -> None:
    shp = fetch_ne_layer("roads")
    log.info("reading %s", shp)
    gdf = gpd.read_file(shp)

    # type column varies in NE schema
    type_col = next(
        (c for c in ["type", "TYPE", "featurecla", "FEATURECLA"] if c in gdf.columns),
        None,
    )
    if type_col is None:
        gdf["road_class"] = "tertiary"
        gdf["speed_kph"] = 50
    else:
        types = gdf[type_col].fillna("Unknown").tolist()
        gdf["road_class"] = [ROAD_CLASS_MAP.get(t, ("tertiary", 50))[0] for t in types]
        gdf["speed_kph"]  = [ROAD_CLASS_MAP.get(t, ("tertiary", 50))[1] for t in types]

    # Drop ferries — they double-count maritime; skip.
    gdf = gdf[gdf["road_class"] != "ferry"].copy()

    gdf["mode"] = "road"
    gdf["from_mode"] = "road"
    gdf["to_mode"] = "road"
    gdf["length_km"] = gdf.geometry.apply(line_length_km)
    gdf = gdf[gdf["length_km"] > 0].copy()

    gdf = tag_country(gdf)

    keep = ["mode", "from_mode", "to_mode", "length_km", "iso_a2", "road_class", "speed_kph", "geometry"]
    gdf = gdf[keep]

    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    log.info("wrote %d road edges -> %s", len(gdf), out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
