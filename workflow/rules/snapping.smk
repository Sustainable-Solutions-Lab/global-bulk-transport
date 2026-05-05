"""Cropland-filtered destination grid + cached snapping."""

rule build_dest_grid:
    output: PROC / "dest_cells.parquet"
    shell:
        "python -m global_bulk_transport.snapping.dest_grid --out {output}"

rule snap_destinations:
    input:
        graph = PROC / "graph_weighted.pkl",
        cells = PROC / "dest_cells.parquet",
    output: PROC / "dest_snapped.parquet"
    shell:
        "python -m global_bulk_transport.snapping.snap_dests "
        "--graph {input.graph} --cells {input.cells} --out {output}"
