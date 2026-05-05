"""Print summary statistics of the assembled multimodal graph.

Useful for sanity-checking after a build. Run ``pixi run graph-stats``.
"""
from __future__ import annotations

import pickle
from collections import Counter
from pathlib import Path

import numpy as np

from global_bulk_transport.config import path


def main() -> None:
    p = Path(path("data_processed")) / "graph_weighted.pkl"
    if not p.exists():
        p = Path(path("data_processed")) / "graph.pkl"
    g = pickle.load(p.open("rb"))
    print(f"graph: V={g.vcount():,}  E={g.ecount():,}  ({p})")

    print("\nedges by mode:")
    for mode, n in sorted(Counter(g.es["mode"]).items(), key=lambda kv: -kv[1]):
        print(f"  {mode:18s} {n:>9,}")

    L = np.array([float(x or 0) for x in g.es["length_km"]])
    print(f"\ntotal network length: {L.sum():,.0f} km  (median edge {np.median(L):,.1f} km)")

    if "cost_total" in g.edge_attributes():
        C = np.array([float(x or 0) for x in g.es["cost_total"]])
        K = np.array([float(x or 0) for x in g.es["co2_total"]])
        for label, arr in (("cost_total (USD)", C), ("co2_total (g)", K)):
            print(f"  {label:24s} min={arr.min():.4g}  median={np.median(arr):.4g}  max={arr.max():.4g}")

    comps = g.connected_components()
    sizes = sorted([len(c) for c in comps], reverse=True)
    print(f"\nconnected components: {len(sizes):,}")
    print(f"  largest covers {sizes[0]:,} / {g.vcount():,} = {sizes[0]/g.vcount():.1%}")
    print(f"  next sizes: {sizes[1:6]}")


if __name__ == "__main__":
    main()
