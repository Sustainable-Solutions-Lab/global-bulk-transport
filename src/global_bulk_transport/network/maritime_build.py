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

K_NEAREST = 20       # short-haul: each port to its K nearest neighbours
MAX_LEG_KM = 20000   # ~half the planet

# Global bulk hub ports — every port connects to its 2 nearest hubs, and
# all hubs are fully connected among themselves. This guarantees realistic
# trans-ocean edges (Shanghai-LongBeach, Rotterdam-Houston etc.) without
# blowing up the edge count to N^2.
HUB_PORTS = [
    ("Rotterdam",     4.40, 51.92),
    ("Singapore",   103.85,  1.27),
    ("Shanghai",    121.47, 31.23),
    ("Houston",     -95.27, 29.75),
    ("Hampton Roads", -76.30, 36.95),
    ("Long Beach",  -118.20, 33.77),
    ("Tubarão",      -40.25, -20.30),
    ("Cape Town",     18.42, -33.92),
    ("Yokohama",     139.65, 35.45),
    ("Sydney",       151.20, -33.86),
    ("Mumbai",        72.83, 18.95),
    ("Hamburg",        9.99, 53.55),
    ("New Orleans",  -90.07, 29.95),
    ("Vancouver",   -123.10, 49.28),
    ("Dakar",        -17.45, 14.67),
    ("Buenos Aires", -58.40, -34.60),
    ("Suez Canal N",  32.30, 31.25),
    ("Panama Canal N", -79.92, 9.35),
    ("Reykjavik",    -21.94, 64.15),
    ("Auckland",     174.78, -36.84),
]


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


def _emit_edge(
    edges_rows: list[dict],
    seen: set[tuple[int, int]],
    i: int, j: int,
    coords: np.ndarray,
    ports: gpd.GeoDataFrame,
) -> None:
    a, b = (i, j) if i < j else (j, i)
    if (a, b) in seen:
        return
    seen.add((a, b))
    gc = great_circle_km(tuple(coords[i]), tuple(coords[j]))
    sea = _searoute(coords[i, 0], coords[i, 1], coords[j, 0], coords[j, 1])
    if sea is None:
        # searoute could not find a feasible sea path. We deliberately do
        # NOT fall back to great-circle here: a great-circle "edge" from a
        # Great Lakes port to a Gulf-of-Mexico port (1600 km) would be a
        # phantom shortcut that bypasses the real St Lawrence + Atlantic
        # detour (5500 km). Skip the edge; multi-hop SSSP will route via
        # an intermediate port that searoute does support.
        return
    dist_km, route_coords = sea
    if len(route_coords) < 2:
        return
    # Inland-river ports (e.g. Wuhan on the Yangtze in NE 10m ports) make
    # searoute return a too-short path that doesn't even start at the
    # requested origin. Reject those.
    first_dist = great_circle_km(route_coords[0], tuple(coords[i]))
    if dist_km < 0.9 * gc or first_dist > 100.0:
        return
    line = LineString(
        [tuple(coords[i]), *route_coords[1:-1], tuple(coords[j])]
    )
    edges_rows.append({
        "mode": "maritime",
        "from_mode": "port",
        "to_mode":   "port",
        "length_km": dist_km,
        "iso_a2": None,
        "from_port_id": int(ports.iloc[i]["port_id"]),
        "to_port_id":   int(ports.iloc[j]["port_id"]),
        "geometry": line,
    })


def _hub_indices(coords: np.ndarray) -> list[int]:
    """Return the port-index in the input coords array that's nearest to
    each ``HUB_PORTS`` location."""
    out = []
    for _, hub_lon, hub_lat in HUB_PORTS:
        d = np.hypot(coords[:, 0] - hub_lon, coords[:, 1] - hub_lat)
        out.append(int(d.argmin()))
    # dedupe (some hubs may map to the same port)
    return sorted(set(out))


def build(ports_path: Path, out: Path) -> None:
    ports = gpd.read_file(ports_path).set_crs("EPSG:4326", allow_override=True)
    n = len(ports)
    coords = np.array([(p.x, p.y) for p in ports.geometry])

    edges_rows: list[dict] = []
    seen: set[tuple[int, int]] = set()

    # 1) K-nearest short-haul edges
    log.info("phase 1: K=%d nearest-neighbour edges over %d ports", K_NEAREST, n)
    for i in range(n):
        d_gc = np.array([
            great_circle_km(tuple(coords[i]), tuple(coords[j])) if j != i else np.inf
            for j in range(n)
        ])
        for j in np.argsort(d_gc)[:K_NEAREST]:
            if d_gc[j] <= MAX_LEG_KM and j != i:
                _emit_edge(edges_rows, seen, i, int(j), coords, ports)

    # 2) Hub-hub complete subgraph + every-port-to-2-nearest-hubs
    hub_idxs = _hub_indices(coords)
    log.info("phase 2: hub-hub complete subgraph over %d hubs + 2-nearest-hub spokes",
             len(hub_idxs))
    for ai in range(len(hub_idxs)):
        for bi in range(ai + 1, len(hub_idxs)):
            i, j = hub_idxs[ai], hub_idxs[bi]
            d = great_circle_km(tuple(coords[i]), tuple(coords[j]))
            if d <= MAX_LEG_KM:
                _emit_edge(edges_rows, seen, i, j, coords, ports)

    hub_pts = coords[hub_idxs]
    for i in range(n):
        if i in hub_idxs:
            continue
        d_to_hubs = np.array([
            great_circle_km(tuple(coords[i]), tuple(hp)) for hp in hub_pts
        ])
        for k in np.argsort(d_to_hubs)[:2]:
            j = hub_idxs[int(k)]
            if d_to_hubs[k] <= MAX_LEG_KM:
                _emit_edge(edges_rows, seen, i, j, coords, ports)

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
