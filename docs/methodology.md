# Methodology and assumptions

This is the **single central document** for methodology and quantitative
assumptions. Code does not duplicate these numbers; it reads them from
`config/co2.yaml`, `config/cost.yaml`, `config/transshipment.yaml` and
`config/inland_waterways.geojson`.

## 1. Project scope

The project produces, for every (source, destination) pair on a global
network, three end-to-end quantities:

1. transport **distance** (km)
2. transport **monetary cost** for *bulk minerals* (USD, 2020–2024 reference)
3. transport **CO2 emissions** (g CO2)

The network is **multimodal**: heavy-truck road, freight rail, inland
waterway barge, and ocean bulk shipping, with explicit transshipment
edges between modes carrying their own cost and CO2 penalties.

The intended downstream use is research on Enhanced Rock Weathering
(ERW), where one needs to combine quarry-source data with destination
agricultural cells under realistic logistics constraints. The transport
layer is, however, a standalone artefact — mineral type, grade, dose
rate and CO2 sequestration belong elsewhere.

## 2. Network construction (Phase 1)

### 2.1 Scope-of-work decision: not running Open-GIRA on a planet OSM file

The original spec envisions cloning [`nismod/open-gira`](https://github.com/nismod/open-gira)
and running its road / rail / maritime network-creation rules on a recent
OSM planet file (~80 GB compressed). On a single workstation in a
day-scale build that is not feasible. We therefore mirror Open-GIRA's
*structure* (separate per-mode rules, per-country tagging, a final
multimodal merge) but seed each mode with **pre-cleaned global
infrastructure datasets**:

| Mode | Source | Notes |
|------|--------|-------|
| Road | Natural Earth 10m roads + (optional) GRIP v4 | NE for default skeleton; GRIP slot wired in `workflow/rules/road.smk` if user wants higher-resolution |
| Rail | Natural Earth 10m railroads | sufficient for global SSSP at 0.5° destination grid |
| Maritime | World Port Index (NGA) ports + great-circle / `searoute` distances | searoute respects continental land masses |
| Inland waterway | hand-encoded GeoJSON (config/inland_waterways.geojson) | per spec; 25 systems |

The Snakemake interface is identical to a planet-OSM run: any future
user can drop in Open-GIRA outputs (GeoPackages with the same edge/node
schema) and the rest of the pipeline works unchanged. See
`workflow/rules/road.smk` for the swap point.

### 2.1.1 Road network densification ("stitching")

Natural Earth 10m roads is highway-only and contains digitisation
gaps where two roads should join at a junction but don't share an
exact endpoint. Without correction the resulting graph fragments into
~5 000 disconnected components covering only ~60 % of road nodes.

We add a deterministic stitching pass (``network/road_stitch.py``)
that, for each road endpoint, adds short edges to its 4 nearest road
endpoints within 80 km. After stitching, ~99 % of all multimodal
nodes lie in a single connected component (down from ~60 %). Stitch
edges are tagged ``road_class="stitch"`` so they can be filtered out
of any analysis that wants the original NE topology.

This is the same operation snkit's `add_endpoints_within` /
`split_at_intersections` would do. We keep it as an explicit small
step here so the densification is auditable.

### 2.1.2 Maritime endpoint snapping

The ``searoute`` library returns sea routes whose start/end coords
are sea-graph nodes a few km off the actual port lon/lat. We
explicitly overwrite the LineString endpoints with the port's exact
coords so port-node identity (``port_<lon>_<lat>``) is preserved when
the multimodal graph is assembled — without this, every Atlantic
crossing port falls into a different component.

### 2.2 Country tagging and length

Edge-level `country` is assigned by spatial join against Natural Earth
admin-0 boundaries; segments crossing borders are split. Lengths
(`length_km`) are computed on the WGS84 ellipsoid via `pyproj.Geod`,
yielding sub-percent error globally without requiring local projections.

### 2.3 Inland waterway layer

Hand-encoded as `config/inland_waterways.geojson`. We encode 25 major
bulk-freight inland systems (vs. trying to extract every navigable
river from OSM/HydroSHEDS, which is what the spec warns against). Each
LineString carries:

- `name`, `country`, `system_id`
- `cemt_class` (or local equivalent encoded to CEMT for cost/CO2 lookup)
- `max_barge_tonnage`
- `notes` (linkage to source: PIANC, USACE, CCNR, country agency)

Class assignments follow:

- **Europe** — CEMT classification: PIANC + CCNR (Rhine), Donaucommission (Danube)
  ([CEMT classes](https://en.wikipedia.org/wiki/CEMT_class)).
- **United States** — USACE waterway classes mapped to nearest CEMT
  equivalent (Mississippi main stem ≈ CEMT VIb; Ohio ≈ CEMT VIa;
  Tennessee/Cumberland ≈ CEMT Va; Illinois ≈ CEMT Vb).
- **China** — Class III–I (national), Yangtze main below Yichang ≈ CEMT VIa.
- **Russia** — UVVP class IV–I; Volga–Don main stem ≈ CEMT VIa.
- **South America** — Paraná/Paraguay convoys ≈ CEMT VIb in barge
  capacity but with CEMT IV/V draft restrictions; encoded conservatively.

Rationale: barge tonnage drives per-tkm cost and CO2, and class is the
most defensible single coarse parameter.

### 2.4 Transshipment edges

At every port, every river-port and at rail/road junctions we add
**zero-length** edges connecting nodes in different modes. Each carries
a fixed cost (USD/t) and CO2 (kg/t) drawn from
`config/transshipment.yaml`. Without these penalties, multi-modal
SSSP flips between modes spuriously (a 5 km truck leg "cheaper" than a
5 km rail leg with no transfer cost).

Connection rule: a port is connected to road and rail nodes within the
radius set in `config.yaml#transshipment_link_radius_km`. River ports
are auto-detected as inland-waterway endpoints intersected with port
locations OR with rail/road within the river-port radius.

## 3. Cost & CO2 attribution (Phase 2)

### 3.1 CO2 (g CO2 / tonne-km)

Defaults (see `config/co2.yaml` for the authoritative values and full
citations):

| Mode | g CO2 / tkm | Source |
|------|-------------|--------|
| Heavy bulk truck | 70 | EcoTransIT 2024, IEA Tracking Transport |
| Rail diesel | 28 | EcoTransIT 2024 |
| Rail electric (world avg) | 18 | EcoTransIT 2024 |
| Inland barge (avg) | 32 | PIANC WG156 (2019) |
| Sea handysize | 10 | IMO 4th GHG (2020), EcoTransIT |
| Sea panamax | 4 | IMO 4th GHG |
| Sea capesize | 3 | IMO 4th GHG |

Country grid factors for **electric rail** are applied as
`co2 = grid[g/kWh] × 0.025 [kWh/tkm]`, consistent with EcoTransIT's
freight rail energy intensity. The 0.025 kWh/tkm value is for loaded
heavy freight; passenger and mixed-freight intensity is higher and is
not used.

Country adjustment for **truck** comes from a fleet-age and load-factor
multiplier, conservative ranges from EcoTransIT regional appendices
(e.g. India 1.25, China 1.10, USA 1.05, Germany 0.95). For new
country-mode pairs the default applies.

Inland barge factor varies by encoded CEMT class (small barges have
worse fuel-per-tkm).

Sea CO2 factor is selected dynamically from vessel class which itself is
a function of port-pair great-circle distance (short legs stay
handysize, long legs assume capesize / panamax mix). See
`src/global_bulk_transport/attributes/sea.py`.

### 3.2 Cost (USD / tonne-km, 2020–2024 USD)

Defaults (full table in `config/cost.yaml`):

| Mode | USD / tkm | Source |
|------|-----------|--------|
| Truck bulk | 0.075 | spec range $0.05–0.10; Renforth 2012; Verschuur 2025 OECD avg |
| Rail unit train | 0.018 | spec range $0.01–0.03; Eufrasio 2022 ($0.04 mixed) treated as upper bound |
| Inland barge | 0.0075 | USACE Mississippi grain ~$0.007/tkm |
| Sea bulk | 0.0035 | Drewry / Argus dry-bulk midpoint |

Country multipliers for road, rail and barge are calibrated against:

1. Verschuur et al. (2025) Zenodo deposit `country_road_cost_factors.csv`
   for road,
2. World Bank LPI 2023 logistics-quality and cost components for
   tier-based fallback,
3. published bulk-rail tariff studies (Drewry; AAR; UIC) for rail,
4. USACE / CCNR / Yangtze administration data for barge.

Where Verschuur 2025 publishes a country USD/tkm directly, it is used
in preference to the multiplier; the loader code documents the
resolution order.

The 2020–2024 reference window matters because dry-bulk shipping
spiked over 2021–2022 (BDI). Sea cost values here are the
period-average; users can rescale by today's BDI ÷ 2020–2024 BDI.

### 3.3 Transshipment

Per-tonne handling cost ($1.20–$2.50/t depending on transshipment type)
and CO2 (3.5–7.5 kg/t) — see `config/transshipment.yaml`. These are
applied as edge weights on zero-length cross-mode edges.

## 4. Snapping API (Phase 3)

`snap(lon, lat, mode_preference=None)` returns the nearest network node
within the mode-specific radius set in `config.yaml`. Spatial query
uses an `rtree` over node geometries.

Destination grid is 0.5° world cells filtered to those with cropland
fraction ≥ 5% from ESA WorldCover 2021 aggregated to 0.5° (or, if
WorldCover not provided, a fallback uses the bundled MODIS/SPAM
aggregation in `data/raw/cropland_05deg.tif`). This typically reduces
~64,000 land cells to ~30,000–40,000 destinations. Snapped-destination
node IDs are cached in `data/processed/dest_snapped.parquet`.

## 5. Routing (Phase 4)

For each source we run `igraph.Graph.distances` (Dijkstra) three times,
once per metric (`length_km`, `cost_total`, `co2_total`). The three
shortest paths are different in general — that difference is the
informative signal we want to expose to downstream researchers.

Per-source output: an `xarray.Dataset` with three DataArrays of length
N_dest, written into a single zarr store under
`results/routes.zarr/{source_id}`.

We **do not store paths**, only the terminal scalar values per
destination. This keeps total output to ~0.5 MB × N_sources.

## 6. Visualization (Phase 5)

A FastAPI app (`src.global_bulk_transport.viz.serve`) serves:

- `GET /sources` — list of available source IDs and locations.
- `GET /grid/{source_id}?metric=cost_total|co2_total|length_km` — JSON
  GeoJSON of 0.5° destination cells with the chosen metric.
- `/` — Leaflet HTML page that lets the user pick a source and a metric
  and shades the world map.

Self-contained, runs locally on the host/port from `config.yaml`.

## 7. Bibliography

- **CCNR (2024)** Central Commission for the Navigation of the Rhine,
  *Annual Report on Inland Navigation in Europe*.
- **EcoTransIT World (2024)** Knörr, W., Hüttermann, R., Reuter, C.,
  *EcoTransIT World — Methodology v9*. ifeu / IVE / INFRAS for Hapag-
  Lloyd, DB Schenker, Kühne+Nagel et al.
- **Eufrasio, R. M., Kantzas, E. P., Edwards, N. R., Holden, P. B.,
  Pollitt, H., Mercure, J.-F., Koh, S. C. L., Beerling, D. J. (2022)**
  Environmental and health impacts of atmospheric CO2 removal by
  enhanced rock weathering depend on nations' energy mix.
  *Communications Earth & Environment* 3:1–11.
- **IEA (2023)** *Tracking Transport*. International Energy Agency.
- **IEA (2023)** *Electricity 2023* — country grid CO2 intensities.
- **IMO (2020)** *Fourth IMO GHG Study 2020* (MEPC 75/7/15).
- **NGA / Maritime Safety Office** *World Port Index*, Pub. 150, 2019
  edition (latest open).
- **PIANC (2008)** *Bulk Solid Handling at Inland Terminals*, Working
  Group 156 background.
- **PIANC (2019)** *Greenhouse-gas emissions of inland navigation*,
  Working Group 156 final report.
- **Renforth, P. (2012)** The potential of enhanced weathering in the
  UK. *International Journal of Greenhouse Gas Control* 10:229–243.
- **USACE (2022)** *Inland Waterway Navigation: Value to the Nation*.
  US Army Corps of Engineers, Institute for Water Resources.
- **UNCTAD (2022)** *Review of Maritime Transport 2022*.
- **Verschuur, J. et al. (2025)** *Country-level road freight cost
  factors* — Zenodo dataset (doi pending in deposit).
- **World Bank (2023)** *Logistics Performance Index 2023*.

## 8. Limitations

- Pre-cleaned input layers (Natural Earth) coarsen the road and rail
  network relative to OSM-derived planet output. Where city-scale
  resolution is needed, swap in Open-GIRA outputs via the wired
  Snakemake input slot.
- Sea routing uses `searoute` great-circle-on-sea; piracy zones,
  draft-restricted straits and seasonal Arctic routes are not modelled.
- Inland waterway encoding is curated, not exhaustive — secondary
  basins not in the encoded set are unreachable by barge.
- Cost/CO2 numbers are loaded-only and average factors. Empty-leg and
  congestion variation are not represented.
- Vessel-class-from-distance heuristic is coarse; commodity-flow
  research with a finer fleet model should override `attributes/sea.py`.
