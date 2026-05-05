"""Build per-mode node GeoPackages from edge endpoints.

We deliberately use a coarse rounding-based dedup (5 decimal degrees ~= 1m)
rather than full topological cleaning — the routing fidelity at our 0.5°
destination grid does not warrant a heavier snkit/topojson pass.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def _endpoints(line) -> list[tuple[float, float]]:
    coords = list(line.coords)
    return [coords[0], coords[-1]]


def build_nodes(edges_path: Path, mode: str, out: Path) -> None:
    edges = gpd.read_file(edges_path)
    rows: list[dict] = []
    for geom in edges.geometry:
        if geom is None or geom.is_empty:
            continue
        # MultiLineString: pull endpoints of every part.
        if geom.geom_type == "MultiLineString":
            parts = list(geom.geoms)
        else:
            parts = [geom]
        for part in parts:
            for x, y in _endpoints(part):
                rows.append({"x": round(x, 5), "y": round(y, 5)})
    df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    df["node_id"] = [f"{mode}_{i}" for i in range(len(df))]
    df["mode"] = mode
    df["geometry"] = [Point(x, y) for x, y in zip(df.x, df.y, strict=False)]
    gdf = gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry="geometry", crs="EPSG:4326")
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True)
    p.add_argument("--in", dest="inp", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build_nodes(args.inp, args.mode, args.out)


if __name__ == "__main__":
    main()
