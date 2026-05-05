"""Download helpers for public global infrastructure datasets.

Natural Earth 10m cultural layers are the default seeds for road, rail
and port (and country boundary) layers. They are MIT-licensed-equivalent
public domain and small enough to download in a build.

If the user wants city-resolution or planet-OSM-quality data, they can
drop in pre-built GeoPackages with the same schema (see methodology.md).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import requests

from global_bulk_transport.config import path
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)

NE_BASE = "https://naciscdn.org/naturalearth/10m/cultural"

LAYERS = {
    "roads":     f"{NE_BASE}/ne_10m_roads.zip",
    "railroads": f"{NE_BASE}/ne_10m_railroads.zip",
    "ports":     f"{NE_BASE}/ne_10m_ports.zip",
    "countries": f"{NE_BASE}/ne_10m_admin_0_countries.zip",
}


_SHP_NAME = {
    "roads":     "ne_10m_roads.shp",
    "railroads": "ne_10m_railroads.shp",
    "ports":     "ne_10m_ports.shp",
    "countries": "ne_10m_admin_0_countries.shp",
}


def fetch_ne_layer(layer: str) -> Path:
    """Download a Natural Earth layer to data/raw/ne/<layer>/ and return shapefile path."""
    if layer not in LAYERS:
        raise ValueError(f"unknown NE layer: {layer}; choose from {list(LAYERS)}")
    out_dir = path("data_raw") / "ne" / layer
    shp = out_dir / _SHP_NAME[layer]
    if shp.exists():
        return shp
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("downloading Natural Earth %s ...", layer)
    r = requests.get(LAYERS[layer], timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(out_dir)
    if not shp.exists():
        candidates = list(out_dir.rglob(_SHP_NAME[layer]))
        if candidates:
            shp = candidates[0]
    log.info("wrote %s", shp)
    return shp
