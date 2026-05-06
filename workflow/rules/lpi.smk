"""Fetch LPI 2023+2018 country factors from World Bank API."""

rule fetch_lpi:
    output: "config/lpi_country_factors.csv"
    shell:
        "python -m global_bulk_transport.network.fetch_lpi --out {output}"
