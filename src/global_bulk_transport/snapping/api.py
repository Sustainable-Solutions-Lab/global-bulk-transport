"""Snap (lon, lat) -> nearest network node for a chosen mode preference.

The igraph stored as ``data/processed/graph_weighted.pkl`` carries each
vertex's (x, y) and ``mode``. We build mode-stratified cKDTree indexes
on first use and cache them. ``snap`` returns the node id (igraph vertex
``name``) or ``None`` if no node lies within the configured radius.
"""
from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from global_bulk_transport.config import path, project_config

KM_PER_DEG = 111.0


@lru_cache(maxsize=1)
def _graph():
    p = Path(path("data_processed")) / "graph_weighted.pkl"
    if not p.exists():
        p = Path(path("data_processed")) / "graph.pkl"
    return pickle.load(p.open("rb"))


@lru_cache(maxsize=8)
def _index_for_mode(mode: str | None):
    g = _graph()
    if mode is None:
        idxs = list(range(g.vcount()))
    else:
        idxs = [v.index for v in g.vs if v["mode"] == mode]
    if not idxs:
        return None, None
    pts = np.array([(g.vs[i]["x"], g.vs[i]["y"]) for i in idxs])
    return cKDTree(pts), idxs


def snap(lon: float, lat: float, mode_preference: str | None = None) -> str | None:
    """Snap to the nearest network node honoring ``mode_preference``.

    If ``mode_preference`` is set, snap only to that mode's nodes within
    the radius from ``config.yaml#snap_radius_km``. If ``None``, snap to
    the nearest node in any mode within the road radius (the most
    permissive default — quarry-source coords usually only have road
    access by default).
    """
    cfg = project_config()["snap_radius_km"]
    mode = mode_preference or "road"
    radius_km = float(cfg.get(mode, cfg["road"]))
    tree, idxs = _index_for_mode(None if mode_preference is None else mode_preference)
    if tree is None:
        return None
    dist_deg, j = tree.query([lon, lat], k=1, distance_upper_bound=radius_km / KM_PER_DEG)
    if not np.isfinite(dist_deg):
        return None
    g = _graph()
    return g.vs[idxs[int(j)]]["name"]
