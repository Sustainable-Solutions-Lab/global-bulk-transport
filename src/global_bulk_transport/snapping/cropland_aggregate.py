"""Aggregate the Ramankutty et al. (2008) 5-arcmin cropland fraction
raster to a 0.5° NetCDF/GeoTIFF that ``snapping/dest_grid.py`` can use.

Source: M3-Cropland 2000 (year-2000 cropland-area fraction of grid-cell)
        from EarthStat (Ramankutty 2008, Global Biogeochem. Cycles 22).
Origin URL: https://storage.googleapis.com/earthstat/CroplandPastureArea2000_Geotiff.zip

Aggregation: 6×6 mean → 0.5° = ~55 km resolution at the equator.
Cropland is reported as fractional area in [0,1] so a simple mean is
correct (the underlying data is already a fractional value not a count).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


def aggregate(src_tif: Path, out_tif: Path, target_res_deg: float = 0.5) -> None:
    with rasterio.open(src_tif) as src:
        log.info("source raster: shape=%s res=%.4f deg crs=%s nodata=%s",
                 src.shape, src.transform[0], src.crs, src.nodata)
        if src.crs and "4326" not in str(src.crs):
            raise SystemExit("expected EPSG:4326 source raster")
        src_res = src.transform[0]
        factor = int(round(target_res_deg / src_res))
        if factor < 2:
            raise SystemExit(f"target res {target_res_deg} <= source res {src_res}")
        h, w = src.shape
        # Crop to a multiple of factor.
        nh, nw = (h // factor) * factor, (w // factor) * factor
        band = src.read(1, window=((0, nh), (0, nw)))
        nodata = src.nodata
        if nodata is not None:
            band = np.where(band == nodata, np.nan, band).astype("float32")
        block = band.reshape(nh // factor, factor, nw // factor, factor)
        agg = np.nanmean(block, axis=(1, 3))
        log.info("aggregated to %s (factor %d)", agg.shape, factor)
        # Build target transform
        x0 = src.transform[2]                       # left
        y0 = src.transform[5]                       # top
        new_transform = Affine(
            target_res_deg, 0.0, x0,
            0.0, -target_res_deg, y0,
        )
        out_tif.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            out_tif, "w",
            driver="GTiff",
            height=agg.shape[0],
            width=agg.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=new_transform,
            nodata=np.nan,
            compress="DEFLATE",
        ) as dst:
            dst.write(agg.astype("float32"), 1)
        log.info("wrote %s", out_tif)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path,
                   default=Path("data/raw/earthstat/CroplandPastureArea2000_Geotiff/Cropland2000_5m.tif"))
    p.add_argument("--out", type=Path, default=Path("data/raw/cropland_05deg.tif"))
    p.add_argument("--res", type=float, default=0.5)
    args = p.parse_args()
    aggregate(args.src, args.out, args.res)


if __name__ == "__main__":
    main()
