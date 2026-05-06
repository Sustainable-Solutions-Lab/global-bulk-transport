"""Pixel-wise minimum across all sources in routes.zarr.

For every cropland destination cell and every metric, find the cheapest
source and the cost of reaching it. Output:

    results/envelope.zarr
        coords: dest (cell_id, lon, lat), source (source_id, lon, lat)
        vars:   {metric}_min     -- best cost to that cell
                {metric}_argmin  -- index into the source dim of the winner

The destination grid is already cropland-filtered upstream by
``snapping/dest_grid.py``, so no extra masking is needed here.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr
import zarr

from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)

METRICS = ("length_km", "cost_total", "co2_total")


def aggregate(routes: Path, out: Path) -> None:
    store = zarr.open(str(routes), mode="r")
    source_ids = sorted(store.group_keys())
    if not source_ids:
        raise SystemExit(f"no source groups in {routes}")
    log.info("aggregating %d sources from %s", len(source_ids), routes)

    # All groups share the dest grid; load coords from the first.
    first = xr.open_zarr(routes, group=source_ids[0])
    dest_coords = {
        "cell_id": ("dest", first["cell_id"].values),
        "lon":     ("dest", first["lon"].values),
        "lat":     ("dest", first["lat"].values),
    }
    n_dest = first.sizes["dest"]

    # Stack per-source arrays into (source, dest) per metric.
    stacks: dict[str, np.ndarray] = {
        m: np.full((len(source_ids), n_dest), np.inf, dtype=np.float64) for m in METRICS
    }
    src_lon = np.empty(len(source_ids), dtype=np.float64)
    src_lat = np.empty(len(source_ids), dtype=np.float64)
    src_name = np.empty(len(source_ids), dtype=object)

    for i, sid in enumerate(source_ids):
        ds = xr.open_zarr(routes, group=sid)
        src_lon[i] = float(ds.attrs.get("source_lon", np.nan))
        src_lat[i] = float(ds.attrs.get("source_lat", np.nan))
        src_name[i] = str(ds.attrs.get("source_name", sid))
        for m in METRICS:
            arr = ds[m].values
            arr = np.where(np.isfinite(arr), arr, np.inf)
            stacks[m][i] = arr

    out_vars: dict[str, xr.DataArray] = {}
    for m in METRICS:
        s = stacks[m]
        # Cells with no finite value from any source -> argmin still valid (0)
        # but min is +inf; flag them as NaN in the output for downstream masking.
        all_inf = ~np.isfinite(s).any(axis=0)
        argmin = np.argmin(s, axis=0).astype(np.int32)
        vmin = s[argmin, np.arange(s.shape[1])]
        vmin = np.where(all_inf, np.nan, vmin)
        argmin = np.where(all_inf, -1, argmin).astype(np.int32)

        out_vars[f"{m}_min"] = xr.DataArray(
            vmin, dims=("dest",), coords=dest_coords, attrs={"metric": m},
        )
        out_vars[f"{m}_argmin"] = xr.DataArray(
            argmin, dims=("dest",), coords=dest_coords,
            attrs={"metric": m, "fill_value": -1, "indexes_into": "source"},
        )
        n_reached = int((~all_inf).sum())
        log.info("%s: %d / %d cells reached by at least one source",
                 m, n_reached, n_dest)

    src_arr = np.array(source_ids, dtype=object)
    out_vars["source_id"] = xr.DataArray(src_arr, dims=("source",))
    out_vars["source_lon"] = xr.DataArray(src_lon, dims=("source",))
    out_vars["source_lat"] = xr.DataArray(src_lat, dims=("source",))
    out_vars["source_name"] = xr.DataArray(src_name, dims=("source",))

    ds_out = xr.Dataset(out_vars, attrs={
        "n_sources": len(source_ids),
        "metrics":   list(METRICS),
        "routes_src": str(routes),
    })

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        # zarr's default mode='w' on an existing dir tries to merge — easier
        # to nuke and rewrite for this small artefact.
        import shutil
        shutil.rmtree(out)
    ds_out.to_zarr(out, mode="w")
    log.info("wrote envelope -> %s", out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--routes", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    aggregate(args.routes, args.out)


if __name__ == "__main__":
    main()
