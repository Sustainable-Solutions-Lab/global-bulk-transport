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
    # quantile breaks for color scale
    if len(df) >= 5:
        q = np.quantile(df["v"], [0.05, 0.25, 0.5, 0.75, 0.95])
    else:
        q = np.linspace(df["v"].min() if len(df) else 0, df["v"].max() if len(df) else 1, 5)
    return JSONResponse({
        "source_id": source_id,
        "metric": metric,
        "n": len(df),
        "breaks": q.tolist(),
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
