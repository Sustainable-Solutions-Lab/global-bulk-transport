"""Per-source SSSP × 3 metrics -> zarr store.

For each source row we:
  1. snap to a network node honoring mode_preference
  2. run igraph.Graph.distances() on the source for each weight
  3. gather distance to every snapped destination cell
  4. write three DataArrays into a per-source group inside a single
     zarr store: results/routes.zarr/{source_id}/{length_km|cost_total|co2_total}
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import zarr

from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


METRICS = ["length_km", "cost_total", "co2_total"]


def _snap_via_graph(g, lon: float, lat: float, mode_preference: str | None,
                    snap_radius_km: dict, km_per_deg: float = 111.0) -> int | None:
    from scipy.spatial import cKDTree
    mode = mode_preference if mode_preference else "road"
    radius = float(snap_radius_km.get(mode, snap_radius_km.get("road", 50)))
    if mode_preference is None:
        idxs = list(range(g.vcount()))
    else:
        idxs = [v.index for v in g.vs if v["mode"] == mode_preference]
    if not idxs:
        return None
    pts = np.array([(g.vs[i]["x"], g.vs[i]["y"]) for i in idxs])
    tree = cKDTree(pts)
    d_deg, j = tree.query([lon, lat], k=1, distance_upper_bound=radius / km_per_deg)
    if not np.isfinite(d_deg):
        return None
    return idxs[int(j)]


def run(graph_pkl: Path, dests_pq: Path, sources_csv: Path, out: Path) -> None:
    from global_bulk_transport.config import project_config
    cfg = project_config()
    snap_radii = cfg["snap_radius_km"]

    g = pickle.load(graph_pkl.open("rb"))
    dests = pd.read_parquet(dests_pq)
    sources = pd.read_csv(sources_csv)

    # vertex name -> index lookup
    name_to_idx = {n: i for i, n in enumerate(g.vs["name"])}
    dest_node_idx = np.array(
        [name_to_idx.get(n, -1) for n in dests["snap_node_id"]],
        dtype=np.int64,
    )
    keep = dest_node_idx >= 0
    dests = dests[keep].reset_index(drop=True)
    dest_node_idx = dest_node_idx[keep]
    log.info("destinations resolvable in graph: %d / %d", keep.sum(), len(keep))

    # igraph's distances() rejects duplicate targets. Multiple cells can
    # share a snapped node, so we run SSSP on the unique-node set and
    # then fan back out to all destinations via an inverse index.
    unique_nodes, inv = np.unique(dest_node_idx, return_inverse=True)
    log.info("unique target nodes: %d", len(unique_nodes))

    out.mkdir(parents=True, exist_ok=True)
    store = zarr.open(str(out), mode="a")
    # Marker file Snakemake watches:
    (out / ".zgroup").touch()

    cell_ids = dests["cell_id"].to_numpy()
    cell_lons = dests["lon"].to_numpy()
    cell_lats = dests["lat"].to_numpy()

    for _, src in sources.iterrows():
        sid = src["source_id"]
        s_node = _snap_via_graph(
            g, float(src["lon"]), float(src["lat"]),
            None if pd.isna(src.get("mode_preference")) else src["mode_preference"],
            snap_radii,
        )
        if s_node is None:
            log.warning("source %s could not be snapped; skipping", sid)
            continue

        log.info("routing source %s (snap idx=%d) ...", sid, s_node)
        ds_vars: dict[str, xr.DataArray] = {}
        for metric in METRICS:
            d_unique = g.distances(source=s_node, target=list(unique_nodes), weights=metric)[0]
            arr = np.asarray(d_unique, dtype=np.float64)[inv]
            ds_vars[metric] = xr.DataArray(
                arr, dims=("dest",),
                coords={"cell_id": ("dest", cell_ids),
                        "lon":     ("dest", cell_lons),
                        "lat":     ("dest", cell_lats)},
                attrs={"metric": metric, "source_id": sid},
            )
        ds = xr.Dataset(ds_vars, attrs={
            "source_id": sid,
            "source_lon": float(src["lon"]),
            "source_lat": float(src["lat"]),
            "source_name": str(src.get("name", sid)),
            "snap_node_id": str(g.vs[s_node]["name"]),
        })
        ds.to_zarr(out, group=sid, mode="w")
        log.info("source %s -> %s/%s", sid, out, sid)

    log.info("done")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--dests", type=Path, required=True)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    run(args.graph, args.dests, args.sources, args.out)


if __name__ == "__main__":
    main()
