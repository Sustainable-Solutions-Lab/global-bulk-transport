"""Attach cost & CO2 weights to every edge.

Reads the pickled multimodal igraph, looks up per-mode and per-country
factors from ``config/cost.yaml`` / ``config/co2.yaml`` /
``config/transshipment.yaml``, and writes new edge attributes:

    cost_total          (USD)  = unit_cost(mode, country, class) * length_km
                                 + handling cost (transshipment)
    co2_total           (g)    = unit_co2(mode, country, class)  * length_km
                                 + handling CO2 (transshipment) * 1000 [kg->g]

Edge attribute keys ``cost_unit_usd_per_tkm`` and ``co2_unit_g_per_tkm``
are also kept for transparency / debugging.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import igraph as ig

from global_bulk_transport.attributes.lookup import edge_co2_g_per_tkm, edge_cost_usd_per_tkm
from global_bulk_transport.attributes.sea import sea_cost_co2
from global_bulk_transport.attributes.transshipment import handling
from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)


def attach(graph_in: Path, graph_out: Path) -> None:
    g: ig.Graph = pickle.load(graph_in.open("rb"))
    log.info("loaded graph V=%d E=%d", g.vcount(), g.ecount())

    cost_per_tkm: list[float] = []
    co2_per_tkm:  list[float] = []
    cost_total:   list[float] = []
    co2_total:    list[float] = []

    for e in g.es:
        mode  = e["mode"]
        L     = float(e["length_km"] or 0.0)
        iso   = e["iso_a2"]

        if mode == "transshipment":
            kind = e["transshipment_kind"]
            cost_h, co2_h_kg = handling(kind, iso)
            cost_per_tkm.append(0.0)
            co2_per_tkm.append(0.0)
            cost_total.append(cost_h)
            co2_total.append(co2_h_kg * 1000.0)        # kg -> g
            continue

        if mode == "maritime":
            unit_cost, unit_co2 = sea_cost_co2(L)
            cost_per_tkm.append(unit_cost)
            co2_per_tkm.append(unit_co2)
            cost_total.append(unit_cost * L)
            co2_total.append(unit_co2 * L)
            continue

        unit_cost = edge_cost_usd_per_tkm(mode, iso, e)
        unit_co2  = edge_co2_g_per_tkm(mode,  iso, e)
        cost_per_tkm.append(unit_cost)
        co2_per_tkm.append(unit_co2)
        cost_total.append(unit_cost * L)
        co2_total.append(unit_co2  * L)

    g.es["cost_unit_usd_per_tkm"] = cost_per_tkm
    g.es["co2_unit_g_per_tkm"]    = co2_per_tkm
    g.es["cost_total"]            = cost_total
    g.es["co2_total"]             = co2_total

    graph_out.parent.mkdir(parents=True, exist_ok=True)
    with graph_out.open("wb") as f:
        pickle.dump(g, f)
    log.info("attached cost+CO2; wrote -> %s", graph_out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in",  dest="inp",  type=Path, required=True)
    p.add_argument("--out", dest="outp", type=Path, required=True)
    args = p.parse_args()
    attach(args.inp, args.outp)


if __name__ == "__main__":
    main()
