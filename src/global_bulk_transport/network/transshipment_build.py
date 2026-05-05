"""Build zero-length transshipment edges between modes.

Connection logic (radius from config.yaml#transshipment_link_radius_km):

    port_node       <-> nearest road_node within port_to_road
    port_node       <-> nearest rail_node within port_to_rail
    port_node       <-> nearest inland_waterway_node within port_to_road
                        (i.e. river-port == port that touches an IW system)
    inland_node     <-> nearest road_node within river_to_road
    inland_node     <-> nearest rail_node within river_to_rail
    rail_node       <-> nearest road_node within rail_to_road

Each transshipment edge has length_km = 0, mode tagged with the
ordered mode-pair string used to look up cost/CO2 in
``config/transshipment.yaml``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from global_bulk_transport.config import project_config
from global_bulk_transport.geometry import great_circle_km
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)

# Approx km per degree at equator. We use this for an initial cKDTree
# query in lon/lat space then verify with a great-circle distance, which
# is fine for small radii (<200 km) where curvature matters little.
KM_PER_DEG = 111.0


def _kd(gdf: gpd.GeoDataFrame) -> tuple[cKDTree, np.ndarray]:
    pts = np.array([(g.x, g.y) for g in gdf.geometry])
    return cKDTree(pts), pts


def _connect(
    src_gdf: gpd.GeoDataFrame,
    tgt_gdf: gpd.GeoDataFrame,
    radius_km: float,
    from_mode: str,
    to_mode: str,
    mode_label: str,
    edges_rows: list[dict],
) -> None:
    if len(src_gdf) == 0 or len(tgt_gdf) == 0:
        return
    tree, tgt_pts = _kd(tgt_gdf)
    src_pts = np.array([(g.x, g.y) for g in src_gdf.geometry])
    radius_deg = radius_km / KM_PER_DEG
    # nearest only (k=1) — single transshipment per port/yard pair
    dists_deg, idxs = tree.query(src_pts, k=1, distance_upper_bound=radius_deg)
    for i, (dd, j) in enumerate(zip(dists_deg, idxs, strict=False)):
        if not np.isfinite(dd) or j >= len(tgt_pts):
            continue
        d_km = great_circle_km(tuple(src_pts[i]), tuple(tgt_pts[j]))
        if d_km > radius_km:
            continue
        edges_rows.append({
            "mode": "transshipment",
            "from_mode": from_mode,
            "to_mode": to_mode,
            "transshipment_kind": mode_label,
            "length_km": 0.0,             # zero-length per spec
            "iso_a2": src_gdf.iloc[i].get("iso_a2"),
            "geometry": LineString([tuple(src_pts[i]), tuple(tgt_pts[j])]),
        })


def build(
    road_nodes: Path, rail_nodes: Path, port_nodes: Path, inland_nodes: Path, out: Path
) -> None:
    cfg = project_config()["transshipment_link_radius_km"]
    road = gpd.read_file(road_nodes)
    rail = gpd.read_file(rail_nodes)
    port = gpd.read_file(port_nodes)
    iw = gpd.read_file(inland_nodes)

    # Normalise port nodes to share a node_id column.
    if "node_id" not in port.columns:
        port = port.copy()
        port["node_id"] = ["port_" + str(int(p)) for p in port["port_id"]]

    edges_rows: list[dict] = []
    log.info("connecting ports <-> road (r=%s km)", cfg["port_to_road"])
    _connect(port, road, cfg["port_to_road"], "port", "road", "road_to_sea", edges_rows)
    log.info("connecting ports <-> rail (r=%s km)", cfg["port_to_rail"])
    _connect(port, rail, cfg["port_to_rail"], "port", "rail", "rail_to_sea", edges_rows)
    log.info("connecting ports <-> inland (r=%s km)", cfg["port_to_road"])
    _connect(port, iw,   cfg["port_to_road"], "port", "inland_waterway", "inland_to_sea", edges_rows)
    log.info("connecting inland <-> road (r=%s km)", cfg["river_to_road"])
    _connect(iw,   road, cfg["river_to_road"], "inland_waterway", "road", "road_to_inland", edges_rows)
    log.info("connecting inland <-> rail (r=%s km)", cfg["river_to_rail"])
    _connect(iw,   rail, cfg["river_to_rail"], "inland_waterway", "rail", "rail_to_inland", edges_rows)
    log.info("connecting rail <-> road (r=%s km)", cfg["rail_to_road"])
    _connect(rail, road, cfg["rail_to_road"], "rail", "road", "road_to_rail",  edges_rows)

    edges = gpd.GeoDataFrame(pd.DataFrame(edges_rows), geometry="geometry", crs="EPSG:4326")
    out.parent.mkdir(parents=True, exist_ok=True)
    edges.to_file(out, driver="GPKG")
    log.info("wrote %d transshipment edges -> %s", len(edges), out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--road-nodes", type=Path, required=True)
    p.add_argument("--rail-nodes", type=Path, required=True)
    p.add_argument("--port-nodes", type=Path, required=True)
    p.add_argument("--inland-nodes", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.road_nodes, args.rail_nodes, args.port_nodes, args.inland_nodes, args.out)


if __name__ == "__main__":
    main()
