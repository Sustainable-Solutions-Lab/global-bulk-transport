"""Hand-encoded inland-waterway layer (config/inland_waterways.geojson)."""

rule build_inland:
    input:  "config/inland_waterways.geojson"
    output: PROC / "inland" / "edges.gpkg",
            PROC / "inland" / "nodes.gpkg"
    shell:
        "python -m global_bulk_transport.network.inland_build "
        "--src {input} --edges {output[0]} --nodes {output[1]}"
