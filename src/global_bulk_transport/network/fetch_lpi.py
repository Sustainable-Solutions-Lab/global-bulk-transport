"""Fetch World Bank Logistics Performance Index 2023 by country, derive
country-level cost factors transparently, and write a CSV that
``attributes/lookup.py`` will use in preference to the hand-set values
in ``config/cost.yaml``.

Why this exists: the methodology asks for "Verschuur 2025 Zenodo deposit's
per-country road cost factors as a starting point and scale … plus the
World Bank LPI for country adjustments". Verschuur et al. 2025 (Nature
Food, "Heterogeneities in landed costs of traded grains and oilseeds")
do not publish a per-country USD/tkm road table directly; their landed
costs are aggregated by trade route and grain. The publicly downloadable
proxy is the WB LPI infrastructure component, which Arvis et al. 2018
("Connecting to Compete") show correlates strongly with logistics cost
per tonne-km. We use a transparent monotonic mapping from LPI infra
score to a cost multiplier:

    factor = clip(2.5 / lpi_infra, 0.70, 1.60)

This puts an LPI=3.5 country at factor ~0.71, LPI=3.0 at ~0.83, LPI=2.5
at 1.00, LPI=2.0 at 1.25, LPI=1.5 at 1.60. The mapping is documented
explicitly so users can replace it with the Verschuur 2025 table when
they obtain it.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from global_bulk_transport.logging_setup import get_logger

log = get_logger(__name__)

WB_API = "https://api.worldbank.org/v2/country/all/indicator/{ind}"
INDICATORS = {
    "overall":        "LP.LPI.OVRL.XQ",
    "infrastructure": "LP.LPI.INFR.XQ",
    "intl_shipments": "LP.LPI.ITRN.XQ",
    "logistics":      "LP.LPI.LOGS.XQ",
    "timeliness":     "LP.LPI.TIME.XQ",
}


def _fetch(indicator: str, date_range: str = "2018:2023") -> pd.DataFrame:
    """Return the most recent non-null value per country over ``date_range``.

    WB labels the LPI 2023 publication's data as survey-year 2022, and
    LPI 2018 as 2018. We pick the latest available year per country.
    """
    url = WB_API.format(ind=indicator)
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(
                url,
                params={"date": date_range, "format": "json", "per_page": 2000},
                timeout=120,
            )
            r.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_err = e
            log.warning("WB API attempt %d failed for %s (%s); retrying", attempt + 1, indicator, e)
    else:
        raise RuntimeError(f"failed to fetch {indicator}: {last_err}")
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"unexpected WB API response for {indicator}")
    rows = [r for r in payload[1] if r.get("value") is not None]
    df = pd.DataFrame([
        {
            "iso_a3": row["countryiso3code"],
            "country": row["country"]["value"],
            "year":  int(row["date"]),
            "value": float(row["value"]),
        }
        for row in rows
    ])
    if df.empty:
        return df
    df = df.sort_values(["iso_a3", "year"], ascending=[True, False]).drop_duplicates("iso_a3")
    log.info("fetched %s: %d countries, year mix %s",
             indicator, len(df), df["year"].value_counts().to_dict())
    return df.drop(columns="year")


def _iso3_to_iso2() -> dict[str, str]:
    """Crude ISO3 -> ISO2 lookup for the countries we have road-cost rows for.
    Sourced from `pycountry` if available; fallback to a static common list.
    """
    try:
        import pycountry
        return {c.alpha_3: c.alpha_2 for c in pycountry.countries if hasattr(c, "alpha_2")}
    except ImportError:
        # Static fallback covering ~all WB-reporting countries.
        return _STATIC_ISO3_TO_ISO2


def factor_from_lpi_infra(lpi_infra: float) -> float:
    """Monotonic mapping: lower infrastructure -> higher cost multiplier."""
    if lpi_infra is None or pd.isna(lpi_infra) or lpi_infra <= 0:
        return 1.00
    f = 2.5 / float(lpi_infra)
    return max(0.70, min(1.60, f))


def build(out_csv: Path) -> None:
    log.info("fetching WB LPI 2023 indicators …")
    frames = {name: _fetch(ind) for name, ind in INDICATORS.items()}

    df = frames["overall"][["iso_a3", "country", "value"]].rename(columns={"value": "lpi_overall"})
    for name in ("infrastructure", "intl_shipments", "logistics", "timeliness"):
        d = frames[name][["iso_a3", "value"]].rename(columns={"value": f"lpi_{name}"})
        df = df.merge(d, on="iso_a3", how="outer")

    iso3_to_iso2 = _iso3_to_iso2()
    df["iso_a2"] = df["iso_a3"].map(iso3_to_iso2)
    df = df.dropna(subset=["iso_a2"])

    df["road_cost_factor"] = df["lpi_infrastructure"].apply(factor_from_lpi_infra)
    # Rail/barge/handling: less elastic to LPI in practice; use a milder mapping
    df["rail_cost_factor"] = df["lpi_infrastructure"].apply(
        lambda x: max(0.80, min(1.30, factor_from_lpi_infra(x)))
    )
    df["barge_cost_factor"] = df["lpi_infrastructure"].apply(
        lambda x: max(0.85, min(1.25, factor_from_lpi_infra(x)))
    )
    df["handling_cost_factor"] = df["lpi_infrastructure"].apply(
        lambda x: max(0.80, min(1.40, factor_from_lpi_infra(x)))
    )
    df = df.sort_values("iso_a2").reset_index(drop=True)

    cols = [
        "iso_a2", "iso_a3", "country", "lpi_overall", "lpi_infrastructure",
        "lpi_intl_shipments", "lpi_logistics", "lpi_timeliness",
        "road_cost_factor", "rail_cost_factor", "barge_cost_factor",
        "handling_cost_factor",
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df[cols].to_csv(out_csv, index=False, float_format="%.4f")
    log.info("wrote LPI-derived country factors -> %s (%d countries)", out_csv, len(df))


# Static fallback (only used if pycountry unavailable in the env)
_STATIC_ISO3_TO_ISO2 = {
    "AFG":"AF","ALB":"AL","DZA":"DZ","AGO":"AO","ARG":"AR","ARM":"AM","AUS":"AU",
    "AUT":"AT","AZE":"AZ","BHS":"BS","BHR":"BH","BGD":"BD","BLR":"BY","BEL":"BE",
    "BEN":"BJ","BTN":"BT","BOL":"BO","BIH":"BA","BWA":"BW","BRA":"BR","BRN":"BN",
    "BGR":"BG","BFA":"BF","BDI":"BI","KHM":"KH","CMR":"CM","CAN":"CA","CAF":"CF",
    "TCD":"TD","CHL":"CL","CHN":"CN","COL":"CO","COG":"CG","COD":"CD","CRI":"CR",
    "CIV":"CI","HRV":"HR","CUB":"CU","CYP":"CY","CZE":"CZ","DNK":"DK","DJI":"DJ",
    "DOM":"DO","ECU":"EC","EGY":"EG","SLV":"SV","GNQ":"GQ","ERI":"ER","EST":"EE",
    "ETH":"ET","FIN":"FI","FRA":"FR","GAB":"GA","GMB":"GM","GEO":"GE","DEU":"DE",
    "GHA":"GH","GRC":"GR","GTM":"GT","GIN":"GN","GNB":"GW","GUY":"GY","HTI":"HT",
    "HND":"HN","HKG":"HK","HUN":"HU","ISL":"IS","IND":"IN","IDN":"ID","IRN":"IR",
    "IRQ":"IQ","IRL":"IE","ISR":"IL","ITA":"IT","JAM":"JM","JPN":"JP","JOR":"JO",
    "KAZ":"KZ","KEN":"KE","KOR":"KR","KWT":"KW","KGZ":"KG","LAO":"LA","LVA":"LV",
    "LBN":"LB","LSO":"LS","LBR":"LR","LBY":"LY","LTU":"LT","LUX":"LU","MDG":"MG",
    "MWI":"MW","MYS":"MY","MLI":"ML","MLT":"MT","MRT":"MR","MUS":"MU","MEX":"MX",
    "MDA":"MD","MNG":"MN","MNE":"ME","MAR":"MA","MOZ":"MZ","MMR":"MM","NAM":"NA",
    "NPL":"NP","NLD":"NL","NZL":"NZ","NIC":"NI","NER":"NE","NGA":"NG","NOR":"NO",
    "OMN":"OM","PAK":"PK","PAN":"PA","PNG":"PG","PRY":"PY","PER":"PE","PHL":"PH",
    "POL":"PL","PRT":"PT","QAT":"QA","ROU":"RO","RUS":"RU","RWA":"RW","SAU":"SA",
    "SEN":"SN","SRB":"RS","SLE":"SL","SGP":"SG","SVK":"SK","SVN":"SI","SOM":"SO",
    "ZAF":"ZA","ESP":"ES","LKA":"LK","SDN":"SD","SUR":"SR","SWE":"SE","CHE":"CH",
    "SYR":"SY","TWN":"TW","TJK":"TJ","TZA":"TZ","THA":"TH","TGO":"TG","TUN":"TN",
    "TUR":"TR","TKM":"TM","UGA":"UG","UKR":"UA","ARE":"AE","GBR":"GB","USA":"US",
    "URY":"UY","UZB":"UZ","VEN":"VE","VNM":"VN","YEM":"YE","ZMB":"ZM","ZWE":"ZW",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("config/lpi_country_factors.csv"))
    args = p.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
