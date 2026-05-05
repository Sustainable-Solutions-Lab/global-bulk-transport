"""Stitch micro-gaps in the road network.

Natural Earth 10m roads is a sparse highway-only layer with many
digitisation-level gaps where two roads should join at a junction but
don't share an exact endpoint. We knit endpoints within ``radius_km``
together, producing extra short edges that turn the road network into
something close to a single connected component per land mass.

This is the operation snkit/topojson would do as part of network
cleaning; we keep it here as a small explicit step so the methodology
is transparent.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from global_bulk_transport.geometry import great_circle_km
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)
KM_PER_DEG = 111.0


def stitch(road_edges: Path, road_nodes: Path, out: Path, radius_km: float = 30.0, k: int = 3) -> None:
    nodes = gpd.read_file(road_nodes)
    pts = np.array([(g.x, g.y) for g in nodes.geometry])
    tree = cKDTree(pts)

    radius_deg = radius_km / KM_PER_DEG
    pairs: set[tuple[int, int]] = set()
    for i in range(len(pts)):
        d_deg, idxs = tree.query(pts[i], k=min(k + 1, len(pts)),
                                  distance_upper_bound=radius_deg)
        if np.isscalar(d_deg):
            d_deg, idxs = [d_deg], [idxs]
        for d, j in zip(d_deg, idxs, strict=False):
            if not np.isfinite(d) or j == i or j >= len(pts):
                continue
            a, b = (i, j) if i < j else (j, i)
            pairs.add((a, b))

    rows: list[dict] = []
    for a, b in pairs:
        d_km = great_circle_km(tuple(pts[a]), tuple(pts[b]))
        if d_km > radius_km:
            continue
        rows.append({
            "mode": "road",
            "from_mode": "road",
            "to_mode": "road",
            "length_km": d_km,
            "iso_a2": None,           # stitch edges span both endpoints' country
            "road_class": "stitch",
            "speed_kph": 50,
            "geometry": LineString([tuple(pts[a]), tuple(pts[b])]),
        })

    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry="geometry", crs="EPSG:4326")
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    log.info("wrote %d stitch edges (radius=%.0f km, k=%d) -> %s", len(gdf), radius_km, k, out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--edges", type=Path, required=True)
    p.add_argument("--nodes", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--radius-km", type=float, default=30.0)
    p.add_argument("--k", type=int, default=3)
    args = p.parse_args()
    stitch(args.edges, args.nodes, args.out, args.radius_km, args.k)


if __name__ == "__main__":
    main()
