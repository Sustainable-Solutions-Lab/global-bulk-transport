"""Road network rule.

Default uses Natural Earth 10m roads as the seed; downstream code accepts
a drop-in replacement (same edge/node schema) from Open-GIRA on a planet
OSM file.
"""

rule fetch_road:
    output: PROC / "road" / "edges.gpkg"
    shell:
        "python -m global_bulk_transport.network.road_build "
        "--out {output}"

rule fetch_road_nodes:
    input: PROC / "road" / "edges.gpkg"
    output: PROC / "road" / "nodes.gpkg"
    shell:
        "python -m global_bulk_transport.network.nodes_from_edges "
        "--mode road --in {input} --out {output}"

rule stitch_road:
    input:
        edges = PROC / "road" / "edges.gpkg",
        nodes = PROC / "road" / "nodes.gpkg",
    output: PROC / "road" / "stitch.gpkg"
    shell:
        "python -m global_bulk_transport.network.road_stitch "
        "--edges {input.edges} --nodes {input.nodes} --out {output} "
        "--radius-km 80 --k 4"
