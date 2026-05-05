# global-bulk-transport

Global multimodal bulk-transport graph (road + rail + maritime + inland
waterway) with cost (USD) and CO2 (g) attribution per edge, plus
per-source destination-grid routing for downstream Enhanced Rock
Weathering (ERW) research.

This is the **transport / emissions layer** of a wider ERW project. It
is also independently usable: take a quarry coordinate, get back a 0.5°
global grid of "cheapest" / "lowest-CO2" / "shortest" delivered cost.

## Quick start

```bash
pixi install
pixi run all                 # full pipeline (downloads inputs, builds graph, routes demo sources)
pixi run viz                 # local web map at http://127.0.0.1:8000
```

For step-by-step incremental builds:

```bash
pixi run -- snakemake -d . -s workflow/Snakefile --cores 4 build_graph
pixi run -- snakemake -d . -s workflow/Snakefile --cores 4 attach_attributes
pixi run -- snakemake -d . -s workflow/Snakefile --cores 4 route
```

Running the underlying Python modules directly is also fine — the
Snakemake rules are thin wrappers. See `workflow/rules/*.smk` for the
exact CLI invocations.

After routing completes, the demo zarr store at `results/routes.zarr/`
contains 8 demo source quarries (Iceland, Deccan, Columbia River, Skye,
Paraná, Oman, NY wollastonite, Ethiopia) routed against ~27 000 0.5°
land cells — replace `config/sources_demo.csv` with your own quarries
and re-run.

## What's in here

| Path | Purpose |
|------|---------|
| `config/config.yaml`             | Orchestration parameters (paths, snap radii, grid resolution) |
| `config/cost.yaml`               | USD/tkm cost table with full citations |
| `config/co2.yaml`                | g CO2/tkm CO2 table with full citations |
| `config/transshipment.yaml`      | Per-tonne handling cost & CO2 at multimodal interconnects |
| `config/inland_waterways.geojson`| Hand-encoded major inland-bulk-freight systems |
| `docs/methodology.md`            | **Single central document** for methods, assumptions, citations, limitations |
| `workflow/`                      | Snakemake workflow (per-mode `.smk` rules, mirroring Open-GIRA structure) |
| `tests/`                         | pytest smoke tests (run `pixi run test`) |
| `src/global_bulk_transport/`     | Code |
| `tests/`                         | Smoke tests |

## Design choices and limitations

A complete description lives in `docs/methodology.md` § 8. In short:

- We do **not** run Open-GIRA on a planet OSM file in this repo (not
  feasible at single-workstation timescales). We mirror Open-GIRA's
  per-mode structure but seed each mode with pre-cleaned global
  datasets (Natural Earth roads + railroads, World Port Index ports,
  hand-encoded inland waterways). The Snakemake interface accepts
  drop-in Open-GIRA outputs with the same edge/node schema.
- Cost and CO2 numbers are explicitly 2020–2024 USD reference and per
  the methodology of EcoTransIT (CO2), IMO 4th GHG (sea CO2), USACE
  (barge), Verschuur 2025 (country road cost), and the World Bank LPI
  (country adjustments).
- Outputs store *terminal* per-(source, dest) values (length / cost /
  CO2), not full paths. Re-routing a single source is fast enough that
  storing paths is not worth the disk.

## License

MIT.
