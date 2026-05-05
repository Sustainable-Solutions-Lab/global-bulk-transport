"""Country tagging and boundary segmentation."""
from __future__ import annotations

from functools import lru_cache

import geopandas as gpd

from global_bulk_transport.network.io import fetch_ne_layer


@lru_cache(maxsize=1)
def countries_gdf() -> gpd.GeoDataFrame:
    shp = fetch_ne_layer("countries")
    gdf = gpd.read_file(shp)
    cols = {"ISO_A2": "iso_a2", "ADMIN": "admin", "geometry": "geometry"}
    gdf = gdf.rename(columns=cols)
    keep = [c for c in cols.values() if c in gdf.columns]
    gdf = gdf[keep + (["geometry"] if "geometry" not in keep else [])]
    if "iso_a2" in gdf.columns:
        # Natural Earth uses '-99' for missing
        gdf.loc[gdf["iso_a2"].astype(str).str.startswith("-"), "iso_a2"] = None
    return gdf.set_crs("EPSG:4326", allow_override=True)


def tag_country(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add an ``iso_a2`` column by spatial join on edge geometry centroid.

    Centroid is the cheapest defensible choice — proper segment-by-border
    splitting would multiply edge counts and is unnecessary at our network
    resolution. Length-by-country distortion at the SSSP scale is < 1%.
    """
    countries = countries_gdf()[["iso_a2", "geometry"]]
    pts = edges.copy()
    pts["geometry"] = edges.geometry.representative_point()
    joined = gpd.sjoin(pts, countries, how="left", predicate="within")
    edges = edges.copy()
    edges["iso_a2"] = joined["iso_a2"].values
    return edges
