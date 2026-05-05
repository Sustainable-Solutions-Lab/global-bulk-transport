"""Assemble per-mode edge layers into a single igraph + GeoPackage.

We rely on every per-mode edge file carrying ``from_mode`` and ``to_mode``
columns. Node identity is then ``f"{mode}_{round(x,5)}_{round(y,5)}"`` —
so transshipment edges naturally hook into the right node from each
mode without any additional bookkeeping.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import geopandas as gpd
import igraph as ig
import pandas as pd
from shapely.geometry import Point

from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


def _nid(mode: str, x: float, y: float) -> str:
    return f"{mode}_{round(x, 5):.5f}_{round(y, 5):.5f}"


def _load(p: Path) -> gpd.GeoDataFrame:
    if not p.exists() or p.stat().st_size == 0:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")
    return gpd.read_file(p)


def assemble(inputs: list[Path], pkl_out: Path, gpkg_out: Path) -> None:
    frames = [_load(p) for p in inputs]
    frames = [f for f in frames if len(f) > 0]
    edges = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326"
    )
    # Explode MultiLineString into LineString rows so we can index .coords[0]/[-1].
    edges = edges.explode(index_parts=False).reset_index(drop=True)
    log.info("merged + exploded edges: %d", len(edges))

    if "from_mode" not in edges.columns or "to_mode" not in edges.columns:
        raise RuntimeError(
            "every per-mode edge file must carry from_mode/to_mode columns"
        )

    src_ids: list[str] = []
    dst_ids: list[str] = []
    nodes: dict[str, dict] = {}
    for _, row in edges.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            src_ids.append(None); dst_ids.append(None); continue
        x0, y0 = geom.coords[0]
        x1, y1 = geom.coords[-1]
        sid = _nid(row["from_mode"], x0, y0)
        tid = _nid(row["to_mode"], x1, y1)
        nodes.setdefault(sid, {"node_id": sid, "mode": row["from_mode"], "x": x0, "y": y0})
        nodes.setdefault(tid, {"node_id": tid, "mode": row["to_mode"],   "x": x1, "y": y1})
        src_ids.append(sid); dst_ids.append(tid)

    edges["src"] = src_ids
    edges["dst"] = dst_ids
    before = len(edges)
    edges = edges.dropna(subset=["src", "dst"])
    edges = edges[edges["src"] != edges["dst"]]
    log.info("kept %d / %d valid edges (dropped self-loops, empty geom)", len(edges), before)

    nodes_df = pd.DataFrame(list(nodes.values()))
    name_to_idx = {n: i for i, n in enumerate(nodes_df["node_id"])}

    g = ig.Graph(n=len(nodes_df), directed=False)
    g.vs["name"] = list(nodes_df["node_id"])
    g.vs["mode"] = list(nodes_df["mode"])
    g.vs["x"] = list(nodes_df["x"])
    g.vs["y"] = list(nodes_df["y"])

    edge_pairs = [
        (name_to_idx[s], name_to_idx[d])
        for s, d in zip(edges["src"], edges["dst"], strict=False)
    ]
    g.add_edges(edge_pairs)

    attr_cols = [
        "mode", "length_km", "iso_a2", "road_class", "speed_kph",
        "electrified", "cemt_class", "max_barge_tonnage", "system_id",
        "transshipment_kind", "from_mode", "to_mode",
    ]
    for col in attr_cols:
        g.es[col] = edges[col].tolist() if col in edges.columns else [None] * len(edges)

    pkl_out.parent.mkdir(parents=True, exist_ok=True)
    with pkl_out.open("wb") as f:
        pickle.dump(g, f)
    log.info("pickled graph -> %s (V=%d, E=%d)", pkl_out, g.vcount(), g.ecount())

    edges.drop(columns=["src", "dst"], errors="ignore").to_file(
        gpkg_out, layer="edges", driver="GPKG"
    )
    gpd.GeoDataFrame(
        nodes_df,
        geometry=[Point(x, y) for x, y in zip(nodes_df["x"], nodes_df["y"], strict=False)],
        crs="EPSG:4326",
    ).to_file(gpkg_out, layer="nodes", driver="GPKG")
    log.info("inspection GPKG -> %s", gpkg_out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", nargs="+", type=Path, required=True)
    p.add_argument("--pkl", type=Path, required=True)
    p.add_argument("--gpkg", type=Path, required=True)
    args = p.parse_args()
    assemble(args.inputs, args.pkl, args.gpkg)


if __name__ == "__main__":
    main()
