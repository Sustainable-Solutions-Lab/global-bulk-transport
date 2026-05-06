"""Compare graph port-pair distances against published port-pair distances.

Run: ``pixi run validate-sea``

The reference table is hand-curated from the cargo-aggregator sites
SeaRates, Sea-Distances.org and Breezada. It is not redistributed —
only the numbers are quoted in `docs/validation.md`.

The script emits the full table and a summary mean-absolute-error so a
CI run can spot regressions in the searoute integration or hub topology.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from global_bulk_transport.config import path

# Published distances are in kilometres, reflecting the canonical
# bulk shipping route (Suez canal where applicable; great-circle for
# Pacific & Atlantic).
REFERENCE = [
    ("Rotterdam->Houston",     ( 4.40,  51.92), (-95.27,  29.75), 10450),
    ("Shanghai->Long Beach",   (121.47,  31.23), (-118.20, 33.77), 10654),
    ("Tubarão->Rotterdam",     (-40.25, -20.30), (  4.40,  51.92),  9800),
    ("Singapore->Rotterdam",   (103.75,   1.27), (  4.40,  51.92), 14800),
    ("Singapore->Shanghai",    (103.75,   1.27), (121.47,  31.23),  4200),
    ("Cape Town->Rotterdam",   ( 18.42, -33.92), (  4.40,  51.92), 11200),
    ("Sydney->Yokohama",       (151.20, -33.86), (139.65,  35.45),  8200),
    ("New York->Rotterdam",    (-74.00,  40.66), (  4.40,  51.92),  6300),
    ("Dakar->Rio",             (-17.45,  14.67), (-43.20, -22.90),  6300),
    ("Port Hedland->Qingdao",  (118.57, -20.32), (120.32,  36.07),  7700),
    ("Tubarão->Qingdao",       (-40.25, -20.30), (120.32,  36.07), 23000),
]


def main() -> int:
    g_pkl = Path(path("data_processed")) / "graph_weighted.pkl"
    g = pickle.load(g_pkl.open("rb"))

    port_pts = np.array([(v["x"], v["y"]) for v in g.vs if v["mode"] == "port"])
    port_idxs = [v.index for v in g.vs if v["mode"] == "port"]

    def find(lon, lat):
        d = np.hypot(port_pts[:, 0] - lon, port_pts[:, 1] - lat)
        return port_idxs[int(d.argmin())]

    print(f"\n{'route':35s} {'pub':>10s} {'graph':>10s} {'Δ%':>6s} {'USD/t':>8s}")
    errs: list[float] = []
    for name, (slon, slat), (tlon, tlat), expected in REFERENCE:
        s, t = find(slon, slat), find(tlon, tlat)
        L = g.distances(source=s, target=[t], weights="length_km")[0][0]
        C = g.distances(source=s, target=[t], weights="cost_total")[0][0]
        diff = (L - expected) / expected * 100 if np.isfinite(L) else float("nan")
        errs.append(abs(diff))
        print(f"{name:35s} {expected:>10.0f} {L:>10.0f} {diff:>+5.0f}% {C:>7.2f}")
    print(f"\nmean |Δ|: {np.mean(errs):.1f}%   max |Δ|: {np.max(errs):.1f}%")
    return 0 if np.mean(errs) < 15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
