"""Ad-hoc routing CLI: from an arbitrary lon/lat, return delivered cost /
CO2 / distance to the global destination grid.

Use cases:
  - One-off quarry coordinate that isn't in config/sources_demo.csv.
  - Sanity check ("how expensive is delivery to West Africa from here?").
  - Programmatic interface for downstream ERW research code.

Example:
  pixi run -- python -m global_bulk_transport.routing.query \\
        --lon -118.3 --lat 46.1 --mode rail --top 10
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from global_bulk_transport.config import path, project_config
from global_bulk_transport.snapping.api import _index_for_mode, _graph  # noqa: F401


def _snap_node(g, lon: float, lat: float, mode: str | None) -> int | None:
    from scipy.spatial import cKDTree
    cfg = project_config()["snap_radius_km"]
    snap_mode = mode or "road"
    radius = float(cfg.get(snap_mode, cfg["road"]))
    if mode is None:
        idxs = list(range(g.vcount()))
    else:
        idxs = [v.index for v in g.vs if v["mode"] == mode]
    if not idxs:
        return None
    pts = np.array([(g.vs[i]["x"], g.vs[i]["y"]) for i in idxs])
    tree = cKDTree(pts)
    d_deg, j = tree.query([lon, lat], k=1, distance_upper_bound=radius / 111.0)
    if not np.isfinite(d_deg):
        return None
    return idxs[int(j)]


def query(lon: float, lat: float, metric: str, mode: str | None, top: int) -> pd.DataFrame:
    g_pkl = Path(path("data_processed")) / "graph_weighted.pkl"
    dests_pq = Path(path("data_processed")) / "dest_snapped.parquet"
    g = pickle.load(g_pkl.open("rb"))
    dests = pd.read_parquet(dests_pq)

    src_idx = _snap_node(g, lon, lat, mode)
    if src_idx is None:
        raise SystemExit(f"could not snap source ({lon},{lat}) within configured radius")

    name_to_idx = {n: i for i, n in enumerate(g.vs["name"])}
    target_idxs = np.array([name_to_idx.get(n, -1) for n in dests["snap_node_id"]])
    keep = target_idxs >= 0
    dests = dests[keep].reset_index(drop=True)
    target_idxs = target_idxs[keep]
    unique, inv = np.unique(target_idxs, return_inverse=True)

    d = np.asarray(
        g.distances(source=src_idx, target=list(unique), weights=metric)[0],
        dtype=float,
    )[inv]
    finite = np.isfinite(d)
    out = dests[finite].copy()
    out["value"] = d[finite]
    out = out.sort_values("value")
    return out[["cell_id", "lon", "lat", "value"]].head(top)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--metric", default="cost_total",
                   choices=["length_km", "cost_total", "co2_total"])
    p.add_argument("--mode", default=None,
                   choices=[None, "road", "rail", "inland_waterway", "port"])
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    df = query(args.lon, args.lat, args.metric, args.mode, args.top)
    label = {
        "cost_total": "USD/t", "co2_total": "g CO2/t", "length_km": "km",
    }[args.metric]
    print(f"\nTop {len(df)} cheapest destinations from ({args.lon:.3f}, {args.lat:.3f}) "
          f"by {args.metric} [{label}]:\n")
    for _, r in df.iterrows():
        print(f"  {r['cell_id']:>10s}  ({r['lon']:>7.2f}, {r['lat']:>6.2f})  "
              f"{r['value']:>12,.2f} {label}")


if __name__ == "__main__":
    main()
