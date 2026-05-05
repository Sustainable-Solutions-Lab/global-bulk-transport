"""Build inland-waterway edges + nodes from the hand-encoded GeoJSON."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from global_bulk_transport.geometry import line_length_km
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


def build(src: Path, edges_out: Path, nodes_out: Path) -> None:
    gdf = gpd.read_file(src)
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf["mode"] = "inland_waterway"
    gdf["from_mode"] = "inland_waterway"
    gdf["to_mode"] = "inland_waterway"
    gdf["length_km"] = gdf.geometry.apply(line_length_km)
    gdf = gdf.rename(columns={"country": "iso_a2"})

    keep = [
        "mode", "from_mode", "to_mode", "length_km", "iso_a2",
        "system_id", "name", "cemt_class", "max_barge_tonnage", "geometry",
    ]
    gdf = gdf[keep]

    edges_out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(edges_out, driver="GPKG")
    log.info("wrote %d inland-waterway edges -> %s", len(gdf), edges_out)

    # Nodes: every vertex of every line (segment-level granularity so
    # transshipment edges can attach mid-system to the nearest port).
    rows: list[dict] = []
    for _, row in gdf.iterrows():
        sys_id = row["system_id"]
        for i, (x, y) in enumerate(row.geometry.coords):
            rows.append({
                "node_id": f"iw_{sys_id}_{i}",
                "system_id": sys_id,
                "iso_a2": row["iso_a2"],
                "cemt_class": row["cemt_class"],
                "max_barge_tonnage": row["max_barge_tonnage"],
                "x": round(x, 5),
                "y": round(y, 5),
                "mode": "inland_waterway",
            })
    df = pd.DataFrame(rows)
    df["geometry"] = [Point(x, y) for x, y in zip(df.x, df.y, strict=False)]
    nodes = gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry="geometry", crs="EPSG:4326")
    nodes_out.parent.mkdir(parents=True, exist_ok=True)
    nodes.to_file(nodes_out, driver="GPKG")
    log.info("wrote %d inland-waterway nodes -> %s", len(nodes), nodes_out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--edges", type=Path, required=True)
    p.add_argument("--nodes", type=Path, required=True)
    args = p.parse_args()
    build(args.src, args.edges, args.nodes)


if __name__ == "__main__":
    main()
