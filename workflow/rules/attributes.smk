"""Attach cost & CO2 weights to edges."""

rule attach_attributes:
    input:
        graph = PROC / "graph.pkl",
        lpi   = "config/lpi_country_factors.csv",
    output: PROC / "graph_weighted.pkl"
    shell:
        "python -m global_bulk_transport.attributes.attach "
        "--in {input.graph} --out {output}"
