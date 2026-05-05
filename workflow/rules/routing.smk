"""Three SSSP runs per source -> zarr."""

rule route_sources:
    input:
        graph = PROC / "graph_weighted.pkl",
        dests = PROC / "dest_snapped.parquet",
        sources = "config/sources_demo.csv",
    output:
        directory(RES / "routes.zarr"),
        touch(RES / "routes.zarr" / ".zgroup"),
    shell:
        "python -m global_bulk_transport.routing.run "
        "--graph {input.graph} --dests {input.dests} "
        "--sources {input.sources} --out {output[0]}"
