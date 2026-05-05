"""World Port Index ports."""

rule fetch_ports:
    output: PROC / "ports" / "nodes.gpkg"
    shell:
        "python -m global_bulk_transport.network.ports_build "
        "--out {output}"
