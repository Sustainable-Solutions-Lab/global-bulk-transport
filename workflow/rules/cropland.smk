"""Download Ramankutty 2008 cropland fraction and aggregate to 0.5°."""

rule fetch_cropland:
    output: "data/raw/earthstat/CroplandPastureArea2000_Geotiff.zip"
    shell:
        "mkdir -p data/raw/earthstat && "
        "curl -sL --max-time 600 -o {output} "
        "'https://storage.googleapis.com/earthstat/CroplandPastureArea2000_Geotiff.zip'"

rule unzip_cropland:
    input: "data/raw/earthstat/CroplandPastureArea2000_Geotiff.zip"
    output: "data/raw/earthstat/CroplandPastureArea2000_Geotiff/Cropland2000_5m.tif"
    shell: "unzip -o -d data/raw/earthstat {input}"

rule aggregate_cropland:
    input: "data/raw/earthstat/CroplandPastureArea2000_Geotiff/Cropland2000_5m.tif"
    output: "data/raw/cropland_05deg.tif"
    shell:
        "python -m global_bulk_transport.snapping.cropland_aggregate "
        "--src {input} --out {output}"
