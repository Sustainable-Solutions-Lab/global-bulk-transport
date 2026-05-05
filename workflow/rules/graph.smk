"""Assemble the multimodal igraph + GeoPackage."""

rule assemble_graph:
    input:
        PROC / "road" / "edges.gpkg",
        PROC / "road" / "stitch.gpkg",
        PROC / "rail" / "edges.gpkg",
        PROC / "maritime" / "edges.gpkg",
        PROC / "inland" / "edges.gpkg",
        PROC / "transshipment" / "edges.gpkg",
    output:
        PROC / "graph.pkl",
        PROC / "graph.gpkg",
    shell:
        "python -m global_bulk_transport.network.assemble "
        "--inputs {input} --pkl {output[0]} --gpkg {output[1]}"
