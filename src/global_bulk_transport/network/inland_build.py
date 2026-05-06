"""Build inland-waterway edges + nodes from the hand-encoded GeoJSON.

Each multi-vertex LineString in the GeoJSON is exploded into one
per-segment LineString edge so that intermediate waypoints become graph
nodes and cross-system junctions (Ohio meeting Mississippi at Cairo IL,
etc.) connect topologically. Without this, a densified system would
appear in the graph as a single arc from first to last waypoint.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from global_bulk_transport.geometry import line_length_km
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


def _segments(line: LineString) -> list[LineString]:
    coords = list(line.coords)
    return [LineString([coords[i], coords[i + 1]]) for i in range(len(coords) - 1)]


def build(src: Path, edges_out: Path, nodes_out: Path) -> None:
    gdf = gpd.read_file(src)
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf = gdf.rename(columns={"country": "iso_a2"})

    seg_rows: list[dict] = []
    for _, row in gdf.iterrows():
        for seg in _segments(row.geometry):
            seg_rows.append({
                "mode": "inland_waterway",
                "from_mode": "inland_waterway",
                "to_mode": "inland_waterway",
                "iso_a2": row["iso_a2"],
                "system_id": row["system_id"],
                "name": row["name"],
                "cemt_class": row["cemt_class"],
                "max_barge_tonnage": row["max_barge_tonnage"],
                "length_km": line_length_km(seg),
                "geometry": seg,
            })
    edges = gpd.GeoDataFrame(
        pd.DataFrame(seg_rows), geometry="geometry", crs="EPSG:4326"
    )
    edges_out.parent.mkdir(parents=True, exist_ok=True)
    edges.to_file(edges_out, driver="GPKG")
    log.info(
        "wrote %d inland-waterway edges (from %d systems) -> %s",
        len(edges), len(gdf), edges_out,
    )
    gdf = edges    # for the node-emission below to use the per-segment data

    # Nodes: deduped endpoints of every per-segment edge.
    seen: dict[tuple[float, float], dict] = {}
    for _, row in gdf.iterrows():
        coords = list(row.geometry.coords)
        for x, y in coords:
            key = (round(x, 5), round(y, 5))
            seen.setdefault(key, {
                "node_id": f"iw_{key[0]}_{key[1]}",
                "system_id": row["system_id"],
                "iso_a2": row["iso_a2"],
                "cemt_class": row["cemt_class"],
                "max_barge_tonnage": row["max_barge_tonnage"],
                "x": key[0],
                "y": key[1],
                "mode": "inland_waterway",
            })
    df = pd.DataFrame(list(seen.values()))
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
