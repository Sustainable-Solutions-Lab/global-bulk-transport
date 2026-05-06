"""Render per-source surfaces or the multi-source envelope to PNG.

Run:
  ``pixi run figure``                                  # default per-source
  ``pixi run figure-envelope``                         # envelope (min + argmin)
  ``python -m global_bulk_transport.viz.figure --mode envelope --metric co2_total``

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

METRICS = ["length_km", "cost_total", "co2_total"]


def render_source(source: str, metric: str, out: Path) -> None:
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


def render_envelope(metric: str, out: Path) -> None:
    env_path = Path(path("results")) / "envelope.zarr"
    ds = xr.open_zarr(env_path)
    vmin = ds[f"{metric}_min"].values
    argmin = ds[f"{metric}_argmin"].values
    lons = ds["lon"].values
    lats = ds["lat"].values
    src_lon = ds["source_lon"].values
    src_lat = ds["source_lat"].values

    finite = np.isfinite(vmin) & (argmin >= 0)
    if not finite.any():
        raise SystemExit(f"no reached cells for {metric}")

    fig, axes = plt.subplots(2, 1, figsize=(12, 11), constrained_layout=True)

    # Top: cheapest cost to reach each cell.
    ax = axes[0]
    sc = ax.scatter(
        lons[finite], lats[finite],
        c=vmin[finite], s=6, marker="s", cmap="viridis",
        vmin=np.quantile(vmin[finite], 0.02),
        vmax=np.quantile(vmin[finite], 0.98),
    )
    ax.scatter(src_lon, src_lat, c="red", s=10, marker="*",
               edgecolors="black", linewidths=0.3, zorder=5, label="sources")
    ax.set_xlim(-180, 180); ax.set_ylim(-60, 80); ax.set_aspect("equal")
    ax.set_title(f"Envelope — minimum {metric} across {len(src_lon)} sources")
    plt.colorbar(sc, ax=ax, fraction=0.025, pad=0.02).set_label(f"min({metric})")
    ax.grid(alpha=0.2, linestyle=":")
    ax.legend(loc="lower left", fontsize=9)

    # Bottom: which source wins each cell — categorical.
    # tab20 cycles every 20 sources; that's plenty distinct for 200 if we
    # only need to see the supply-basin structure, not exact identities.
    ax = axes[1]
    cmap = plt.get_cmap("tab20")
    colors = cmap(argmin[finite] % 20)
    ax.scatter(lons[finite], lats[finite], c=colors, s=6, marker="s")
    ax.scatter(src_lon, src_lat, c="black", s=18, marker="*",
               edgecolors="white", linewidths=0.4, zorder=5)
    ax.set_xlim(-180, 180); ax.set_ylim(-60, 80); ax.set_aspect("equal")
    ax.set_title(f"Supply basins — winning source per cell ({metric})")
    ax.grid(alpha=0.2, linestyle=":")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    print(f"wrote {out}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["source", "envelope"], default="source")
    p.add_argument("--source", default=None,
                   help="source_id (required for --mode source)")
    p.add_argument("--metric", default="cost_total", choices=METRICS)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    figdir = Path(path("results")) / "figures"
    if args.mode == "source":
        if not args.source:
            raise SystemExit("--source required for --mode source")
        out = args.out or figdir / f"{args.source}_{args.metric}.png"
        render_source(args.source, args.metric, out)
    else:
        out = args.out or figdir / f"envelope_{args.metric}.png"
        render_envelope(args.metric, out)


if __name__ == "__main__":
    main()
