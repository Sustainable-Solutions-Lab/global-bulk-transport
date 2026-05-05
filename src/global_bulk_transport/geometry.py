"""Geodesic length helpers used everywhere."""
from __future__ import annotations

import numpy as np
from pyproj import Geod
from shapely.geometry import LineString, Point

_GEOD = Geod(ellps="WGS84")


def line_length_km(geom) -> float:
    """Return geodesic length of a (Multi)LineString in kilometres."""
    if geom is None or geom.is_empty:
        return 0.0
    if geom.geom_type == "MultiLineString":
        return float(sum(line_length_km(part) for part in geom.geoms))
    xs, ys = zip(*geom.coords, strict=False)
    _, _, dist_m = _GEOD.inv(xs[:-1], ys[:-1], xs[1:], ys[1:])
    return float(np.sum(dist_m)) / 1000.0


def great_circle_km(p1: Point | tuple, p2: Point | tuple) -> float:
    """Great-circle distance between two lon/lat points (km)."""
    if isinstance(p1, Point):
        p1 = (p1.x, p1.y)
    if isinstance(p2, Point):
        p2 = (p2.x, p2.y)
    _, _, m = _GEOD.inv(p1[0], p1[1], p2[0], p2[1])
    return float(m) / 1000.0
