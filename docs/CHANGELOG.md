# Build journal

## First pass (initial spec build)

End-to-end pipeline: scaffolding → multimodal graph (road / rail /
maritime / inland-waterway / transshipment) → cost & CO₂ attribution →
0.5° destination grid → snapping → SSSP × 3 metrics → FastAPI + Leaflet
viz. ~2 700 LOC, 8 demo sources routed against ~27 000 destinations,
methodology + bibliography in `docs/methodology.md`. See commit
`1e479e9`.

The first pass openly cut several spec corners. A self-comparison
against the spec (delivered to the user) flagged these as the highest-
leverage gaps; the second pass below addresses each with real data
work, validation and tests.

## Second pass — closing the gaps

### Data sources actually integrated (vs. cited but hand-set)

| Item | First pass | Second pass |
|------|-----------|-------------|
| Cropland filter | "fallback: keep all land cells; user supplies raster" | Auto-downloads Ramankutty et al. 2008 M3-Cropland 2000 5-arcmin GeoTIFF from EarthStat, aggregates to 0.5° via `snapping/cropland_aggregate.py`; ~20 000 cropland cells, 16 000 road-snappable destinations |
| Country adjustments | ~20 hand-set yaml multipliers labelled "calibrated against Verschuur 2025 / WB LPI" | `network/fetch_lpi.py` pulls WB LPI 2023 (with 2018 fallback) for 155 countries via the World Bank Indicator API, derives `factor = clip(2.5 / lpi_infrastructure, 0.70, 1.60)`. Hand-set yaml takes precedence for ~20 countries with stronger domain priors; LPI applies for the long tail. |
| Verschuur 2025 dataset | claim of "calibrated against" | Honest acknowledgement in methodology + fetch_lpi.py docstring that the spec's referenced Verschuur 2025 paper (`Heterogeneities in landed costs of traded grains and oilseeds`) does not publish per-country USD/tkm road cost factors directly; LPI infrastructure component is the publicly-derivable proxy. |

### Real bugs surfaced & fixed by validation work

External validation against published port-pair distances surfaced
three real bugs:

1. **NE 10m ports include inland river ports** (Wuhan-on-Yangtze,
   Pittsburgh-on-Ohio). When `searoute` was queried for routes from
   these "ports", it returned nonsensical 60-70 km paths whose start
   coord didn't match the requested origin. Fix: reject searoute
   outputs whose first coord is > 100 km from the requested origin or
   whose distance is < 90 % of the great-circle distance.

2. **Searoute-failure fallback was creating phantom edges.** When
   searoute couldn't find a sea route between (e.g.) a Great Lakes port
   and a Gulf-of-Mexico port, the code fell back to a great-circle
   1623 km Erie→NOLA "maritime" edge, bypassing the real ~5500 km
   St-Lawrence-Atlantic-Gulf detour. Fix: skip such edges entirely;
   multi-hop SSSP routes via supported intermediate ports.

3. **Hand-encoded inland waterways were single arcs in the graph.** A
   28-waypoint Mississippi from St-Louis to NOLA was emitted as ONE
   graph edge (between first and last coord), and the intermediate
   waypoints were geometric only — they couldn't serve as junction
   nodes for cross-system connections (Ohio meeting Mississippi at
   Cairo IL). Fix: in `inland_build.py`, explode each LineString into
   per-segment edges. Ohio + Mississippi now form a connected barge
   network spanning 2 000+ km.

### Topology improvements

- **Maritime hub-and-spoke**: 20 fixed global hub ports + complete-
  subgraph among hubs + 2-nearest-hubs spoke from every other port.
  Without this, K=20 nearest-neighbour-only produced "Aleutian
  stepping-stone" routes for trans-Pacific traffic.
- **Empirical long-haul overrides**: small lookup of canonical
  published distances applied to direct hub-hub edges (Cape Town-
  Rotterdam, Singapore-Rotterdam etc), with 50 km tolerance to handle
  the gap between nominal hub coords and actual NE port coords.
- **Densified inland-waterway geometries**: Mississippi, Rhine,
  Yangtze, Volga, Paraná-Paraguay, Amazon went from 4-9 waypoints to
  19-28, properly tracing the river bends. 45 systems → 292 graph
  edges (was 45).

### Validation harness

- `routing/inspect.py` extracts and pretty-prints the actual edge
  sequence chosen by SSSP for any (source, destination) pair, broken
  down by mode.
- `routing/validate_sea.py` (`pixi run validate-sea`) compares 11
  published port-pair distances against the graph. Mean absolute
  error: 10.5 % (was a phantom-edge-affected nonsense before fix).
- New smoke tests assert: Pittsburgh→NOLA uses ≥ 800 km of barge,
  Iceland→Rotterdam uses ≥ 1 500 km of maritime, the validate-sea
  mean-Δ stays < 15 %, LPI factors are loaded with sane bounds.
- 12/12 tests pass.

### End-to-end Snakemake

Verified `pixi run all` reproduces the full pipeline from a clean
`data/processed/` (downloads of NE / cropland / LPI cached). 17/17
rules execute in ≈ 2 minutes once raw inputs are cached.

### What's still imperfect

- `searoute`'s sea graph cuts shortcuts on a handful of Suez-routed
  corridors (Singapore-Rotterdam, Tubarão-Qingdao) that the empirical
  override fixes for the direct hub-hub edge but cannot fix for SSSP
  multi-hop paths through under-estimated stepping-stones. Would need
  an AIS-derived sea network (e.g. Cerdeiro et al. 2020) to fully
  resolve.
- Verschuur 2025's underlying per-country road cost data is not openly
  redistributed; the LPI proxy is documented as a substitute.
- 1.2 % of multimodal nodes (mostly islands and arctic ports) remain
  in disconnected components.

The full validation table, residual error analysis and citations live
in `docs/validation.md`.
