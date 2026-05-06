"""Local FastAPI app: pick a source on the map, see cost/CO2/distance grid.

Run: ``pixi run viz``  ->  http://127.0.0.1:8000
"""
from __future__ import annotations

import pickle
import threading
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import uvicorn
import xarray as xr
import zarr
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from global_bulk_transport.config import path, project_config

app = FastAPI(title="global-bulk-transport viz")

ROUTES_PATH = Path(path("results")) / "routes.zarr"
GRAPH_PATH = Path(path("data_processed")) / "graph_weighted.pkl"
EDGES_GPKG = Path(path("data_processed")) / "graph.gpkg"
DESTS_PATH = Path(path("data_processed")) / "dest_snapped.parquet"
STATIC_DIR = Path(__file__).resolve().parent / "static"

METRICS = ("length_km", "cost_total", "co2_total")

# Routing artefacts are heavy (graph pickle + edges GPKG ≈ tens of MB and
# several seconds to load). We lazy-load on first /route request and cache
# module-globally; the lock prevents concurrent first-loads from doubling
# memory use.
_routing_lock = threading.Lock()
_graph = None
_edges_gdf = None
_name_to_idx: dict[str, int] | None = None
_dests_df = None

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _open_store():
    if not ROUTES_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"routes.zarr not built yet at {ROUTES_PATH}; run `pixi run route`",
        )
    return zarr.open(str(ROUTES_PATH), mode="r")


@app.get("/sources")
def list_sources():
    store = _open_store()
    out = []
    for sid in store.group_keys():
        ds = xr.open_zarr(ROUTES_PATH, group=sid)
        out.append({
            "source_id": sid,
            "name": ds.attrs.get("source_name", sid),
            "lon":  float(ds.attrs.get("source_lon", float("nan"))),
            "lat":  float(ds.attrs.get("source_lat", float("nan"))),
        })
    return out


@app.get("/grid/{source_id}")
def grid(source_id: str, metric: str = "cost_total"):
    if metric not in ("length_km", "cost_total", "co2_total"):
        raise HTTPException(400, f"unknown metric {metric}")
    if not ROUTES_PATH.exists():
        raise HTTPException(503, "routes.zarr not yet built")
    try:
        ds = xr.open_zarr(ROUTES_PATH, group=source_id)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, f"source {source_id} not in store") from e

    arr = ds[metric].values
    lons = ds["lon"].values
    lats = ds["lat"].values
    finite = np.isfinite(arr)
    df = pd.DataFrame({
        "lon": lons[finite],
        "lat": lats[finite],
        "v": arr[finite],
    })
    if len(df) == 0:
        return JSONResponse({
            "source_id": source_id, "metric": metric, "n": 0,
            "breaks": [], "stats": {}, "histogram": [], "top": [], "cells": [],
        })

    # Quantile breaks for the colour scale; 9 stops give a smooth gradient.
    q = np.quantile(df["v"], np.linspace(0.02, 0.98, 9))
    stats = {
        "min": float(df["v"].min()),
        "p10": float(np.quantile(df["v"], 0.10)),
        "median": float(df["v"].median()),
        "mean": float(df["v"].mean()),
        "p90": float(np.quantile(df["v"], 0.90)),
        "max": float(df["v"].max()),
    }
    # Histogram for the sidebar mini-chart (24 bins, span the q02–q98 range).
    hist_edges = np.linspace(q[0], q[-1], 25)
    hist_counts, _ = np.histogram(df["v"], bins=hist_edges)
    histogram = [
        {"x0": float(hist_edges[i]), "x1": float(hist_edges[i+1]), "n": int(hist_counts[i])}
        for i in range(len(hist_counts))
    ]
    top = (
        df.nsmallest(min(8, len(df)), "v")
          .to_dict(orient="records")
    )
    return JSONResponse({
        "source_id": source_id,
        "metric": metric,
        "n": len(df),
        "breaks": q.tolist(),
        "stats": stats,
        "histogram": histogram,
        "top": top,
        "cells": df.to_dict(orient="records"),
    })


def _load_routing_artefacts():
    """Load + cache the weighted graph, edges GPKG, and dest snap table.

    The igraph edge order matches the GPKG row order by construction (see
    ``network/assemble.py``: both come from the same post-filter DataFrame),
    so igraph edge index ``eid`` indexes directly into ``_edges_gdf``.
    """
    global _graph, _edges_gdf, _name_to_idx, _dests_df
    with _routing_lock:
        if _graph is None:
            if not GRAPH_PATH.exists():
                raise HTTPException(503, f"weighted graph missing at {GRAPH_PATH}")
            with GRAPH_PATH.open("rb") as f:
                _graph = pickle.load(f)
            _name_to_idx = {n: i for i, n in enumerate(_graph.vs["name"])}
        if _edges_gdf is None:
            if not EDGES_GPKG.exists():
                raise HTTPException(503, f"edges GPKG missing at {EDGES_GPKG}")
            _edges_gdf = gpd.read_file(EDGES_GPKG, layer="edges")
            if len(_edges_gdf) != _graph.ecount():
                raise HTTPException(
                    500,
                    f"edges GPKG has {len(_edges_gdf)} rows but graph has "
                    f"{_graph.ecount()} edges; rebuild required",
                )
        if _dests_df is None and DESTS_PATH.exists():
            _dests_df = pd.read_parquet(DESTS_PATH)
    return _graph, _edges_gdf, _name_to_idx, _dests_df


def _edge_coords(eid: int) -> list[list[float]]:
    """Return [[lon, lat], ...] for edge ``eid``. Falls back to a straight
    segment between the two endpoint nodes if geometry is missing."""
    geom = _edges_gdf.geometry.iloc[eid]
    if geom is not None and not geom.is_empty:
        if geom.geom_type == "MultiLineString":
            out: list[list[float]] = []
            for line in geom.geoms:
                out.extend([float(x), float(y)] for x, y in line.coords)
            return out
        return [[float(x), float(y)] for x, y in geom.coords]
    e = _graph.es[eid]
    s, t = e.source, e.target
    return [
        [float(_graph.vs[s]["x"]), float(_graph.vs[s]["y"])],
        [float(_graph.vs[t]["x"]), float(_graph.vs[t]["y"])],
    ]


def _snap_dest_node(lon: float, lat: float) -> tuple[int | None, float, float]:
    """Match the clicked cell back to its pre-computed dest snap (so the
    drawn route corresponds exactly to the cell value displayed)."""
    if _dests_df is None or len(_dests_df) == 0:
        return None, lon, lat
    # Cells live on a 0.5° grid centred on .25/.75; nearest in L1 is exact.
    d = (_dests_df["lon"] - lon).abs() + (_dests_df["lat"] - lat).abs()
    sel = _dests_df.iloc[int(d.argmin())]
    if d.iloc[int(d.argmin())] > 0.6:  # not actually one of our cells
        return None, lon, lat
    return _name_to_idx.get(sel["snap_node_id"]), float(sel["lon"]), float(sel["lat"])


@app.get("/route/{source_id}")
def route(source_id: str, lon: float, lat: float, metric: str = "cost_total"):
    if metric not in METRICS:
        raise HTTPException(400, f"unknown metric {metric}")
    g, edges, name_to_idx, _ = _load_routing_artefacts()

    try:
        ds = xr.open_zarr(ROUTES_PATH, group=source_id)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, f"source {source_id} not in routes store") from e

    src_name = ds.attrs.get("snap_node_id")
    s_idx = name_to_idx.get(src_name) if src_name else None
    if s_idx is None:
        raise HTTPException(404, f"source {source_id} snap node not in graph")

    t_idx, dest_lon, dest_lat = _snap_dest_node(lon, lat)
    if t_idx is None:
        raise HTTPException(404, "destination cell not found in dest_snapped table")

    eids = g.get_shortest_paths(v=s_idx, to=t_idx, weights=metric, output="epath")[0]
    if not eids:
        return JSONResponse({
            "type": "FeatureCollection", "features": [], "by_mode": [],
            "totals": {m: 0.0 for m in METRICS},
            "src": [float(g.vs[s_idx]["x"]), float(g.vs[s_idx]["y"])],
            "dst": [float(g.vs[t_idx]["x"]), float(g.vs[t_idx]["y"])],
            "click": [lon, lat], "dest_cell": [dest_lon, dest_lat],
        })

    features = []
    by_mode: dict[str, dict] = {}
    for eid in eids:
        e = g.es[eid]
        mode = e["mode"]
        length_km = float(e["length_km"] or 0.0)
        cost_total = float(e["cost_total"] or 0.0)
        co2_total = float(e["co2_total"] or 0.0)
        # Skip transshipment hops in the geometry layer — they have zero
        # length and would just stack a marker on top of the port node.
        if mode != "transshipment":
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": _edge_coords(eid)},
                "properties": {
                    "mode": mode,
                    "length_km": length_km,
                    "cost_total": cost_total,
                    "co2_total": co2_total,
                },
            })
        agg = by_mode.setdefault(
            mode, {"mode": mode, "edges": 0, "length_km": 0.0,
                   "cost_total": 0.0, "co2_total": 0.0},
        )
        agg["edges"] += 1
        agg["length_km"] += length_km
        agg["cost_total"] += cost_total
        agg["co2_total"] += co2_total

    totals = {
        "length_km":  sum(m["length_km"]  for m in by_mode.values()),
        "cost_total": sum(m["cost_total"] for m in by_mode.values()),
        "co2_total":  sum(m["co2_total"]  for m in by_mode.values()),
    }
    return JSONResponse({
        "type": "FeatureCollection",
        "features": features,
        "by_mode": sorted(by_mode.values(), key=lambda r: -r["length_km"]),
        "totals": totals,
        "src": [float(g.vs[s_idx]["x"]), float(g.vs[s_idx]["y"])],
        "dst": [float(g.vs[t_idx]["x"]), float(g.vs[t_idx]["y"])],
        "click": [lon, lat],
        "dest_cell": [dest_lon, dest_lat],
    })


@app.get("/", response_class=HTMLResponse)
def index():
    html = (Path(__file__).resolve().parent / "static" / "index.html").read_text()
    return html


def main() -> None:
    cfg = project_config()["viz"]
    uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_level="info")


if __name__ == "__main__":
    main()
