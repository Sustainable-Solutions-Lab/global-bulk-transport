"""Maritime port-to-port edges via searoute (continental-mass-aware)."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from global_bulk_transport.geometry import great_circle_km
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)

# We do NOT build the all-pairs N^2 maritime graph. Instead, for each
# port we connect to the K nearest ports (within a great-circle radius
# cap). This is consistent with how Open-GIRA's AIS-derived port-pair
# matrix looks empirically — most cargo moves on a sparse subset of
# port pairs, and the multimodal SSSP fills in any missing pair via
# detours through intermediate hubs at negligible extra cost.

K_NEAREST = 20       # outbound edges per port; ensures inter-basin connectivity
MAX_LEG_KM = 15000   # reject implausibly long single-leg edges (~half the planet)


def _searoute(lon1: float, lat1: float, lon2: float, lat2: float):
    """Return (distance_km, list[(lon,lat)]) for sea route or None."""
    try:
        import searoute as sr
        origin = [lon1, lat1]
        destination = [lon2, lat2]
        route = sr.searoute(origin, destination, units="km")
        if route is None:
            return None
        coords = route["geometry"]["coordinates"]
        # searoute can return lon/lat or [lon, lat] either way; ensure floats
        coords = [(float(c[0]), float(c[1])) for c in coords]
        dist = float(route["properties"]["length"])
        return dist, coords
    except Exception:
        return None


def build(ports_path: Path, out: Path) -> None:
    ports = gpd.read_file(ports_path).set_crs("EPSG:4326", allow_override=True)
    n = len(ports)
    log.info("building maritime edges over %d ports (K=%d)", n, K_NEAREST)

    coords = np.array([(p.x, p.y) for p in ports.geometry])
    edges_rows: list[dict] = []

    for i in range(n):
        # Compute great-circle distance to every other port; pick K nearest.
        d_gc = np.array([
            great_circle_km(tuple(coords[i]), tuple(coords[j])) if j != i else np.inf
            for j in range(n)
        ])
        nearest = np.argsort(d_gc)[:K_NEAREST]
        for j in nearest:
            if j <= i:                       # build undirected edges once
                continue
            if d_gc[j] > MAX_LEG_KM:
                continue
            sea = _searoute(coords[i, 0], coords[i, 1], coords[j, 0], coords[j, 1])
            if sea is None:
                # fall back to great-circle (over-land; transshipment
                # penalties + alternatives mostly suppress these legs)
                line = LineString([tuple(coords[i]), tuple(coords[j])])
                dist_km = float(d_gc[j])
            else:
                dist_km, route_coords = sea
                if len(route_coords) < 2:
                    continue
                # Force endpoints to land EXACTLY on the port coords; the
                # searoute graph's nearest sea-node may be a few km off
                # which would break port-node identity in the assembled
                # multimodal graph.
                line = LineString(
                    [tuple(coords[i]), *route_coords[1:-1], tuple(coords[j])]
                )

            edges_rows.append({
                "mode": "maritime",
                "from_mode": "port",
                "to_mode":   "port",
                "length_km": dist_km,
                "iso_a2": None,            # high-seas; country not meaningful
                "from_port_id": int(ports.iloc[i]["port_id"]),
                "to_port_id":   int(ports.iloc[j]["port_id"]),
                "geometry": line,
            })

    edges = gpd.GeoDataFrame(pd.DataFrame(edges_rows), geometry="geometry", crs="EPSG:4326")
    out.parent.mkdir(parents=True, exist_ok=True)
    edges.to_file(out, driver="GPKG")
    log.info("wrote %d maritime edges -> %s", len(edges), out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ports", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    build(args.ports, args.out)


if __name__ == "__main__":
    main()
