"""Snap every destination cell to its nearest road node, once."""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from global_bulk_transport.config import project_config
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)
KM_PER_DEG = 111.0


def snap(graph_pkl: Path, cells_pq: Path, out: Path) -> None:
    g = pickle.load(graph_pkl.open("rb"))
    road_idxs = [v.index for v in g.vs if v["mode"] == "road"]
    if not road_idxs:
        raise RuntimeError("no road-mode vertices in graph")
    pts = np.array([(g.vs[i]["x"], g.vs[i]["y"]) for i in road_idxs])
    tree = cKDTree(pts)

    cells = pd.read_parquet(cells_pq)
    radius_km = float(project_config()["snap_radius_km"]["road"])
    dists_deg, idxs = tree.query(
        cells[["lon", "lat"]].to_numpy(),
        k=1,
        distance_upper_bound=radius_km / KM_PER_DEG,
    )
    cells["snap_node_id"] = [
        g.vs[road_idxs[int(j)]]["name"] if np.isfinite(d) and j < len(road_idxs) else None
        for d, j in zip(dists_deg, idxs, strict=False)
    ]
    cells["snap_dist_km"] = [
        float(d) * KM_PER_DEG if np.isfinite(d) else None for d in dists_deg
    ]
    cells = cells.dropna(subset=["snap_node_id"]).reset_index(drop=True)
    log.info(
        "snapped %d cells to road nodes (within %s km)",
        len(cells), radius_km,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    cells.to_parquet(out, index=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--cells", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    snap(args.graph, args.cells, args.out)


if __name__ == "__main__":
    main()
