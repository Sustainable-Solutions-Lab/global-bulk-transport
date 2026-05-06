"""Random-source envelope: per-cell cheapest source over a random sample."""

# Defaults; override via config.yaml -> envelope: { n_sources, seed }
ENV_CFG = config.get("envelope", {})
N_SOURCES = int(ENV_CFG.get("n_sources", 200))
SEED      = int(ENV_CFG.get("seed", 0))

RANDOM_SOURCES_CSV = "config/sources_random.csv"
ROUTES_RANDOM      = RES / "routes_random.zarr"
ENVELOPE_ZARR      = RES / "envelope.zarr"


rule sample_sources:
    output: RANDOM_SOURCES_CSV
    shell:
        "python -m global_bulk_transport.sources.sample "
        f"-n {N_SOURCES} --seed {SEED} --out {{output}}"


rule route_random:
    input:
        graph   = PROC / "graph_weighted.pkl",
        dests   = PROC / "dest_snapped.parquet",
        sources = RANDOM_SOURCES_CSV,
    output:
        directory(ROUTES_RANDOM),
        touch(ROUTES_RANDOM / ".zgroup"),
    shell:
        "python -m global_bulk_transport.routing.run "
        "--graph {input.graph} --dests {input.dests} "
        "--sources {input.sources} --out {output[0]}"


rule aggregate_envelope:
    input:
        ROUTES_RANDOM / ".zgroup",
    output:
        directory(ENVELOPE_ZARR),
        touch(ENVELOPE_ZARR / ".zgroup"),
    shell:
        "python -m global_bulk_transport.analysis.envelope "
        f"--routes {ROUTES_RANDOM} --out {{output[0]}}"


rule envelope:
    input: ENVELOPE_ZARR / ".zgroup"
