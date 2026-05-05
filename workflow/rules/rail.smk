"""Rail network rule. Natural Earth 10m railroads as seed."""

rule fetch_rail:
    output: PROC / "rail" / "edges.gpkg"
    shell:
        "python -m global_bulk_transport.network.rail_build "
        "--out {output}"

rule fetch_rail_nodes:
    input: PROC / "rail" / "edges.gpkg"
    output: PROC / "rail" / "nodes.gpkg"
    shell:
        "python -m global_bulk_transport.network.nodes_from_edges "
        "--mode rail --in {input} --out {output}"
