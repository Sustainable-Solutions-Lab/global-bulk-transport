"""Multimodal interconnect / transshipment edges."""

rule build_transshipment:
    input:
        road_nodes  = PROC / "road" / "nodes.gpkg",
        rail_nodes  = PROC / "rail" / "nodes.gpkg",
        port_nodes  = PROC / "ports" / "nodes.gpkg",
        inland_nodes= PROC / "inland" / "nodes.gpkg",
    output:
        PROC / "transshipment" / "edges.gpkg"
    shell:
        "python -m global_bulk_transport.network.transshipment_build "
        "--road-nodes {input.road_nodes} --rail-nodes {input.rail_nodes} "
        "--port-nodes {input.port_nodes} --inland-nodes {input.inland_nodes} "
        "--out {output}"
