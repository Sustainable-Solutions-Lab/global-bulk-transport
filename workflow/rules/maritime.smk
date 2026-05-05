"""Port-to-port maritime edges via searoute (continental-mass-aware sea distances)."""

rule build_maritime:
    input:  PROC / "ports" / "nodes.gpkg"
    output: PROC / "maritime" / "edges.gpkg"
    shell:
        "python -m global_bulk_transport.network.maritime_build "
        "--ports {input} --out {output}"
