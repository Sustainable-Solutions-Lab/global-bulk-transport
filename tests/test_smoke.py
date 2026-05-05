"""End-to-end-ish smoke tests. Heavy steps assume a build has been run."""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RES = ROOT / "results"


def test_config_loads():
    from global_bulk_transport.config import co2_config, cost_config, transshipment_config
    cost_config()
    co2_config()
    transshipment_config()


def test_inland_geojson_valid():
    import json
    p = ROOT / "config" / "inland_waterways.geojson"
    j = json.loads(p.read_text())
    assert j["type"] == "FeatureCollection"
    assert len(j["features"]) >= 20    # spec asks for ~20-30 systems
    classes = {f["properties"]["cemt_class"] for f in j["features"]}
    assert "VIb" in classes
    assert all(f["properties"].get("max_barge_tonnage", 0) > 0 for f in j["features"])


def test_geometry_length_handles_multilines():
    from shapely.geometry import LineString, MultiLineString
    from global_bulk_transport.geometry import line_length_km
    a = LineString([(0, 0), (1, 0)])
    b = MultiLineString([a, LineString([(2, 0), (3, 0)])])
    assert line_length_km(a) > 100  # ~111 km/deg at equator
    assert line_length_km(b) > 200


def test_lookup_resolves_country():
    from global_bulk_transport.attributes.lookup import edge_co2_g_per_tkm, edge_cost_usd_per_tkm

    class E(dict):
        def __getitem__(self, k):
            return super().get(k)

    # India trucks expensive-cheap & high CO2 vs OECD baseline
    e = E({"electrified": False, "cemt_class": None})
    cost_us = edge_cost_usd_per_tkm("road", "US", e)
    cost_ng = edge_cost_usd_per_tkm("road", "NG", e)
    assert cost_us < cost_ng       # NG factor 1.40 > US factor 0.95
    co2_in = edge_co2_g_per_tkm("road", "IN", e)
    co2_de = edge_co2_g_per_tkm("road", "DE", e)
    assert co2_in > co2_de         # IN factor 1.25 > DE factor 0.95


def test_handling_canonical():
    from global_bulk_transport.attributes.transshipment import handling
    cost1, co1 = handling("road_to_rail", "US")
    cost2, co2 = handling("rail_to_road", "US")    # symmetric form
    assert cost1 == cost2 and co1 == co2


@pytest.mark.skipif(not (PROC / "graph_weighted.pkl").exists(), reason="build not run")
def test_built_graph_has_all_modes():
    g = pickle.load((PROC / "graph_weighted.pkl").open("rb"))
    modes = {e["mode"] for e in g.es}
    assert {"road", "rail", "maritime", "inland_waterway", "transshipment"} <= modes
    cost = np.array(g.es["cost_total"], dtype=float)
    co2 = np.array(g.es["co2_total"], dtype=float)
    assert (cost >= 0).all() and (co2 >= 0).all()


@pytest.mark.skipif(not (PROC / "graph_weighted.pkl").exists(), reason="build not run")
def test_query_cli_returns_results():
    from global_bulk_transport.routing.query import query
    df = query(-118.3, 46.1, "cost_total", "road", top=5)
    assert len(df) == 5
    assert (df["value"].diff().dropna() >= 0).all()  # sorted ascending
    assert df["value"].iloc[0] >= 0


@pytest.mark.skipif(not (RES / "routes.zarr").exists(), reason="routing not run")
def test_routes_metrics_diverge():
    """Length-, cost- and CO2-optimal routes are not perfectly collinear."""
    import xarray as xr

    ds = xr.open_zarr(RES / "routes.zarr", group="basalt_columbia")
    ll = ds["length_km"].values
    ct = ds["cost_total"].values
    co = ds["co2_total"].values
    mask = np.isfinite(ll) & np.isfinite(ct) & np.isfinite(co)
    if mask.sum() < 100:
        pytest.skip("not enough finite routes")
    rho_ll_ct = np.corrcoef(ll[mask], ct[mask])[0, 1]
    rho_ct_co = np.corrcoef(ct[mask], co[mask])[0, 1]
    # Should be highly correlated but never perfectly so:
    assert 0.5 < rho_ll_ct < 0.999
    assert 0.5 < rho_ct_co < 0.9999
