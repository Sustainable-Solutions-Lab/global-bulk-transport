"""Build port nodes GeoPackage from Natural Earth 10m ports.

NE 10m ports include the 1000+ globally significant cargo ports — enough
for a port-to-port maritime SSSP at our resolution. World Port Index
(NGA) has finer detail; not redistributed here for licence reasons.

Schema:
    port_id (int), name, iso_a2, mode='port', geometry (Point)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd

from global_bulk_transport.logging_setup import get_logger
from global_bulk_transport.network.countries import countries_gdf
from global_bulk_transport.network.io import fetch_ne_layer

log = get_logger(__name__)


def build(out: Path) -> None:
    shp = fetch_ne_layer("ports")
    log.info("reading %s", shp)
    gdf = gpd.read_file(shp)

    name_col = next((c for c in ["name", "NAME"] if c in gdf.columns), None)
    if name_col is None:
        gdf["name"] = [f"port_{i}" for i in range(len(gdf))]
    else:
        gdf = gdf.rename(columns={name_col: "name"})

    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    cdf = countries_gdf()[["iso_a2", "geometry"]]
    joined = gpd.sjoin(gdf, cdf, how="left", predicate="within")
    if "iso_a2_left" in joined.columns:
        joined = joined.rename(columns={"iso_a2_left": "iso_a2"})
    if "iso_a2" not in joined.columns:
        # nearest-country fallback (ports in territorial waters)
        joined = gpd.sjoin_nearest(gdf, cdf, how="left")

    out_gdf = joined[["name", "iso_a2", "geometry"]].copy()
    out_gdf["port_id"] = range(len(out_gdf))
    out_gdf["mode"] = "port"

    out.parent.mkdir(parents=True, exist_ok=True)
    out_gdf[["port_id", "name", "iso_a2", "mode", "geometry"]].to_file(out, driver="GPKG")
    log.info("wrote %d port nodes -> %s", len(out_gdf), out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
