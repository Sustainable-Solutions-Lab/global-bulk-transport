"""Build the 0.5° destination cell grid filtered to non-trivial cropland.

We use ESA WorldCover 2021 aggregated to 0.5° if a pre-built
``data/raw/cropland_05deg.tif`` is present (recommended), otherwise we
fall back to a Natural-Earth-land-mask-only filter that keeps every land
cell. The fallback is documented as an inferior approximation in
methodology.md §4.

Output: parquet with columns ``cell_id, lon, lat, cropland_frac``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from global_bulk_transport.config import project_config
from global_bulk_transport.logging_setup import get_logger
from global_bulk_transport.network.countries import countries_gdf

log = get_logger(__name__)


def _grid_centres(res: float) -> pd.DataFrame:
    lons = np.arange(-180 + res / 2, 180, res)
    lats = np.arange(-90 + res / 2, 90, res)
    L, A = np.meshgrid(lons, lats)
    return pd.DataFrame({"lon": L.ravel(), "lat": A.ravel()})


def _cropland_from_raster(raster_path: Path, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    import rasterio

    with rasterio.open(raster_path) as src:
        rows, cols = src.index(lons, lats)
        rows = np.array(rows); cols = np.array(cols)
        valid = (
            (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
        )
        out = np.full(len(lons), np.nan)
        if valid.any():
            band = src.read(1)
            out[valid] = band[rows[valid], cols[valid]].astype(float)
        return out


def build(out: Path) -> None:
    cfg = project_config()["destination_grid"]
    res = float(cfg["resolution_deg"])
    threshold = float(cfg["cropland_threshold"])

    df = _grid_centres(res)
    log.info("global grid centres: %d", len(df))

    # Spatial filter to land
    countries = countries_gdf()
    pts = gpd.GeoDataFrame(
        df, geometry=[Point(x, y) for x, y in zip(df.lon, df.lat, strict=False)],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, countries[["geometry"]], how="left", predicate="within")
    df = df.assign(is_land=joined.index_right.notna().values)
    df = df[df["is_land"]].drop(columns=["is_land"]).reset_index(drop=True)
    log.info("land cells: %d", len(df))

    # Cropland filter
    raster = Path("data/raw/cropland_05deg.tif")
    if raster.exists():
        df["cropland_frac"] = _cropland_from_raster(raster, df.lon.to_numpy(), df.lat.to_numpy())
        df = df[df["cropland_frac"].fillna(0) >= threshold].reset_index(drop=True)
        log.info("cropland >= %.2f cells: %d", threshold, len(df))
    else:
        log.warning(
            "no data/raw/cropland_05deg.tif found; keeping all land cells "
            "(see methodology.md §4 for the recommended ESA WorldCover input)"
        )
        df["cropland_frac"] = np.nan

    df["cell_id"] = [f"d_{i:06d}" for i in range(len(df))]
    df = df[["cell_id", "lon", "lat", "cropland_frac"]]

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    log.info("wrote dest grid -> %s", out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
