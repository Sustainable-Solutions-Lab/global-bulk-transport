"""Extract and inspect actual SSSP paths.

Unlike ``routing/run.py`` (which stores only terminal scalars), this is
a debugging / validation tool: for a single (source, destination) pair,
return the chosen edge sequence by mode and the per-mode contribution to
length / cost / CO2. Used to verify that multimodal routes actually
exercise barge / ship / rail when expected.
"""
from __future__ import annotations

import argparse
import pickle
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from global_bulk_transport.config import path


def _snap(g, lon: float, lat: float, mode: str | None) -> int | None:
    from scipy.spatial import cKDTree

    snap_mode = mode or "road"
    radius_km = 50.0 if snap_mode == "road" else 100.0
    if mode is None:
        idxs = list(range(g.vcount()))
    else:
        idxs = [v.index for v in g.vs if v["mode"] == snap_mode]
    pts = np.array([(g.vs[i]["x"], g.vs[i]["y"]) for i in idxs])
    tree = cKDTree(pts)
    d_deg, j = tree.query([lon, lat], k=1, distance_upper_bound=radius_km / 111.0)
    if not np.isfinite(d_deg):
        return None
    return idxs[int(j)]


def inspect_path(
    src_lon: float, src_lat: float,
    dst_lon: float, dst_lat: float,
    metric: str = "cost_total",
    src_mode: str | None = None,
    dst_mode: str | None = None,
) -> dict:
    g_pkl = Path(path("data_processed")) / "graph_weighted.pkl"
    g = pickle.load(g_pkl.open("rb"))

    s = _snap(g, src_lon, src_lat, src_mode)
    t = _snap(g, dst_lon, dst_lat, dst_mode)
    if s is None or t is None:
        raise SystemExit(f"could not snap source or destination (s={s}, t={t})")

    # Edge IDs along the chosen path
    eids = g.get_shortest_paths(v=s, to=t, weights=metric, output="epath")[0]
    if not eids:
        raise SystemExit("no path found")

    rows: list[dict] = []
    for eid in eids:
        e = g.es[eid]
        rows.append({
            "mode":               e["mode"],
            "transshipment_kind": e["transshipment_kind"],
            "iso_a2":             e["iso_a2"],
            "length_km":          float(e["length_km"] or 0.0),
            "cost_total":         float(e["cost_total"] or 0.0),
            "co2_total":          float(e["co2_total"] or 0.0),
        })
    df = pd.DataFrame(rows)

    by_mode = df.groupby("mode", as_index=False).agg(
        edges=("mode", "size"),
        length_km=("length_km", "sum"),
        cost_total=("cost_total", "sum"),
        co2_total=("co2_total", "sum"),
    ).sort_values("cost_total", ascending=False)

    return {
        "n_edges": len(df),
        "totals": {
            "length_km":  float(df["length_km"].sum()),
            "cost_total": float(df["cost_total"].sum()),
            "co2_total":  float(df["co2_total"].sum()),
        },
        "by_mode": by_mode.to_dict(orient="records"),
        "transshipment_kinds": dict(Counter(
            t for t in df["transshipment_kind"] if t is not None
        )),
        "source_node":      g.vs[s]["name"],
        "destination_node": g.vs[t]["name"],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src-lon", type=float, required=True)
    p.add_argument("--src-lat", type=float, required=True)
    p.add_argument("--dst-lon", type=float, required=True)
    p.add_argument("--dst-lat", type=float, required=True)
    p.add_argument("--metric", default="cost_total",
                   choices=["length_km", "cost_total", "co2_total"])
    p.add_argument("--src-mode", default=None)
    p.add_argument("--dst-mode", default=None)
    args = p.parse_args()

    result = inspect_path(
        args.src_lon, args.src_lat,
        args.dst_lon, args.dst_lat,
        args.metric, args.src_mode, args.dst_mode,
    )
    print(f"\nsource node:       {result['source_node']}")
    print(f"destination node:  {result['destination_node']}")
    print(f"edges along path:  {result['n_edges']}")
    t = result["totals"]
    print(f"\ntotals: {t['length_km']:>10,.1f} km  "
          f"${t['cost_total']:>9,.2f} USD/t  "
          f"{t['co2_total']/1000:>10,.1f} kg CO2/t\n")
    print(f"{'mode':>20s}  {'edges':>5s}  {'km':>10s}  {'USD/t':>9s}  {'kg CO2/t':>10s}")
    for row in result["by_mode"]:
        print(f"  {row['mode']:>18s}  {row['edges']:>5d}  "
              f"{row['length_km']:>10,.1f}  ${row['cost_total']:>8,.2f}  "
              f"{row['co2_total']/1000:>10,.1f}")
    if result["transshipment_kinds"]:
        print("\ntransshipment hops:", result["transshipment_kinds"])


if __name__ == "__main__":
    main()
