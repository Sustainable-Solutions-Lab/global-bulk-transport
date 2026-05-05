"""Attach cost & CO2 weights to edges."""

rule attach_attributes:
    input:  PROC / "graph.pkl"
    output: PROC / "graph_weighted.pkl"
    shell:
        "python -m global_bulk_transport.attributes.attach "
        "--in {input} --out {output}"
