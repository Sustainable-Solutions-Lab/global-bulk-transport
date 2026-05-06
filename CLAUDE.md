# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment & common commands

The project uses **pixi** (conda + pypi). Always invoke tasks through it so the right environment is active.

```bash
pixi install                   # one-time setup
pixi run all                   # full pipeline: build graph -> attach attrs -> route demo sources
pixi run build-graph           # build multimodal igraph + GeoPackage
pixi run weighted              # attach cost/CO2 weights to edges
pixi run route                 # run SSSP for sources_demo.csv -> results/routes.zarr
pixi run viz                   # FastAPI dev map at http://127.0.0.1:8000
pixi run test                  # pytest tests/ (smoke tests; many auto-skip if build hasn't run)
pixi run figure --source <id> --metric <length_km|cost_total|co2_total>
pixi run query -- --lon <x> --lat <y> --metric cost_total --top 10
pixi run validate-sea          # cross-check sea distances vs 11 published port pairs
```

Run a single test: `pixi run -- pytest tests/test_smoke.py::test_lookup_resolves_country -q`.

Incremental Snakemake builds (rules live under `workflow/rules/*.smk`):
`pixi run -- snakemake -s workflow/Snakefile --cores 4 <rule>`. Useful targets: `assemble_graph`, `attach_attributes`, `route_sources`, plus per-mode rules.

Lint: `pixi run -- ruff check src tests` (config in `pyproject.toml`, line length 100, target py311).

## Architecture

The pipeline is a four-stage Snakemake DAG that builds a single multimodal igraph and routes per-source SSSPs against a 0.5° destination grid.

**1. Per-mode edge construction** (`src/global_bulk_transport/network/`, one Python module per mode, mirrored by `workflow/rules/{road,rail,maritime,inland,ports,transshipment}.smk`). Each mode produces a GeoPackage of LineString edges with `from_mode`/`to_mode` columns plus mode-specific attrs (`road_class`, `electrified`, `cemt_class`, …). Sources: Natural Earth 10m for road/rail/ports, hand-encoded `config/inland_waterways.geojson` for IWW, `searoute` for maritime. Road `road_stitch.py` adds short bridge edges within 80 km of dangling endpoints — without this the graph fragments into ~5000 components.

**2. `network/assemble.py`** merges all per-mode GeoPackages into a single `igraph.Graph` (pickled to `data/processed/graph.pkl`) plus an inspection GPKG. **Node identity is `f"{mode}_{round(x,5):.5f}_{round(y,5):.5f}"`** — transshipment edges hook modes together by sharing this string ID with each end, so the per-mode coords must match exactly across files. Don't change the rounding precision without rebuilding everything.

**3. `attributes/attach.py`** decorates each edge with `cost_total` (USD/t) and `co2_total` (g CO2/t). Per-edge USD/tkm and g/tkm come from `attributes/lookup.py`, which reads the YAML tables in `config/{cost,co2,transshipment}.yaml` and applies a country adjustment via the auto-derived World Bank LPI table (`config/lpi_country_factors.csv`, regenerable with `pixi run fetch-lpi`). Hand overrides in YAML take precedence over the LPI factor.

**4. `routing/run.py`** runs three `igraph.distances()` calls per source (one per metric) against the snapped 0.5° destination grid (`snapping/dest_grid.py` + cropland mask from `snapping/cropland_aggregate.py`) and writes per-source xarray groups to `results/routes.zarr/{source_id}/{metric}`. `routing/query.py` is the ad-hoc CLI; `routing/inspect.py` returns full path edge lists for debugging; `routing/validate_sea.py` is the regression check used by `test_sea_distance_validation_within_tolerance`.

`viz/serve.py` is a small FastAPI/Jinja app over the routes.zarr; `viz/figure.py` renders static matplotlib maps for papers.

## Important conventions

- **Numerical assumptions live in YAML, not in code.** `docs/methodology.md` is the single canonical document for every cost/CO2 number, citation, and limitation. When changing rates, edit `config/{cost,co2,transshipment}.yaml` (and the methodology doc), not Python.
- **The CRS for storage is always EPSG:4326.** Lengths are computed via geodesic on the WGS84 ellipsoid (`geometry.line_length_km`), not via planar reprojection.
- **Two graph pickles exist by design**: `graph.pkl` (topology only) is the output of step 2; `graph_weighted.pkl` is the same graph with `cost_total`/`co2_total` per edge from step 3. Routing always uses the weighted one.
- **Snakemake rules are thin shell wrappers around `python -m global_bulk_transport.<module>`** — running modules directly is fine and often faster during development. Look at the `shell:` line in the relevant `.smk` to see exact CLI flags.
- The Snakemake interface intentionally matches Open-GIRA's per-mode edge schema, so swapping in OSM-derived edges (instead of Natural Earth) is meant to be a drop-in replacement at `workflow/rules/road.smk` etc.
- Many tests in `tests/test_smoke.py` are skipped unless a full build has run; don't be alarmed by skips when running tests on a clean checkout.
