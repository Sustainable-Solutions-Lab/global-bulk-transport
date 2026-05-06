"""Generate a random land-only source CSV for the envelope POC.

Produces a CSV with the same schema as ``config/sources_demo.csv`` so
``routing/run.py`` consumes it unchanged. Sampling is area-uniform on the
sphere (lat = arcsin(U[-1,1])) and rejection-tested against the dissolved
Natural Earth land polygon. ``mode_preference`` is left blank so each
source snaps to its nearest network node regardless of mode.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.prepared import prep

from global_bulk_transport.logging_setup import get_logger
from global_bulk_transport.network.countries import countries_gdf

log = get_logger(__name__)


def sample(n: int, seed: int = 0, lat_min: float = -58.0, lat_max: float = 75.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    land = prep(countries_gdf().geometry.union_all())

    # Rejection sampling. Hit rate on land ≈ 0.29; oversample with margin.
    # Asymmetric latitude bounds: keep arctic landmass (Siberia/Alaska
    # extend past 70°N), drop Antarctica (no plausible quarry).
    out: list[tuple[float, float]] = []
    batch = max(4 * n, 256)
    while len(out) < n:
        lon = rng.uniform(-180.0, 180.0, batch)
        lat = np.degrees(np.arcsin(rng.uniform(-1.0, 1.0, batch)))
        for x, y in zip(lon, lat, strict=False):
            if y < lat_min or y > lat_max:
                continue
            if land.contains(Point(x, y)):
                out.append((float(x), float(y)))
                if len(out) >= n:
                    break
    log.info("sampled %d land points", len(out))

    df = pd.DataFrame(out, columns=["lon", "lat"])
    df.insert(0, "source_id", [f"rand_{i:04d}" for i in range(len(df))])
    df["name"] = df["source_id"]
    df["mode_preference"] = ""
    df["notes"] = "random land sample"
    return df[["source_id", "name", "lon", "lat", "mode_preference", "notes"]]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-n", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--lat-min", type=float, default=-58.0,
                   help="exclude points south of this latitude (deg) — default skips Antarctica")
    p.add_argument("--lat-max", type=float, default=75.0,
                   help="exclude points north of this latitude (deg)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    df = sample(args.n, seed=args.seed, lat_min=args.lat_min, lat_max=args.lat_max)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    log.info("wrote %d sources -> %s", len(df), args.out)


if __name__ == "__main__":
    main()
