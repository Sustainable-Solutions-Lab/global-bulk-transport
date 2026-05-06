"""Local FastAPI app: pick a source on the map, see cost/CO2/distance grid.

Run: ``pixi run viz``  ->  http://127.0.0.1:8000
"""
from __future__ import annotations

from pathlib import Path

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
STATIC_DIR = Path(__file__).resolve().parent / "static"

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


@app.get("/", response_class=HTMLResponse)
def index():
    html = (Path(__file__).resolve().parent / "static" / "index.html").read_text()
    return html


def main() -> None:
    cfg = project_config()["viz"]
    uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_level="info")


if __name__ == "__main__":
    main()
