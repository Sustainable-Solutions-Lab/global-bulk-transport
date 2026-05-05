"""Render a per-source cost / CO2 / distance surface to PNG.

Run: ``pixi run figure``  ->  results/figures/<source>_<metric>.png
Useful for the README and methodology doc.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from global_bulk_transport.config import path


def render(source: str, metric: str, out: Path) -> None:
    routes = Path(path("results")) / "routes.zarr"
    ds = xr.open_zarr(routes, group=source)
    arr = ds[metric].values
    lons = ds["lon"].values
    lats = ds["lat"].values
    finite = np.isfinite(arr)
    if not finite.any():
        raise SystemExit(f"no finite values for {source}/{metric}")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    sc = ax.scatter(
        lons[finite], lats[finite],
        c=arr[finite], s=8, marker="s", cmap="viridis",
        vmin=np.quantile(arr[finite], 0.02),
        vmax=np.quantile(arr[finite], 0.98),
    )
    ax.scatter([ds.attrs["source_lon"]], [ds.attrs["source_lat"]],
               c="red", s=80, marker="*", edgecolors="black", linewidths=0.5,
               zorder=5, label="source")
    ax.set_xlim(-180, 180); ax.set_ylim(-60, 80)
    ax.set_aspect("equal")
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title(f"{ds.attrs['source_name']}  —  {metric}")
    cbar = plt.colorbar(sc, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label(metric)
    ax.grid(alpha=0.2, linestyle=":")
    ax.legend(loc="lower left", fontsize=9)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    print(f"wrote {out}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--metric", default="cost_total",
                   choices=["length_km", "cost_total", "co2_total"])
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    out = args.out or Path(path("results")) / "figures" / f"{args.source}_{args.metric}.png"
    render(args.source, args.metric, out)


if __name__ == "__main__":
    main()
