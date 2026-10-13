"""Download every dataset this project uses into data/raw/.

Sources
- California Department of Insurance: home policies new / renewed / dropped by ZIP code
- LA County (ArcGIS Online): CAL FIRE damage inspections joined to parcels, ZIP code
  boundaries, the pre-2025 Fire Hazard Severity Zone maps, and the fire perimeters
"""
import json
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

CDI = "https://www.insurance.ca.gov/01-consumers/200-wrr/upload/"
CDI_FILES = [
    "Residential-Property-Voluntary-Market-New-Renew-NonRenew-by-ZIP-2015-2021.xlsx",
    "Residential-Insurance-Voluntary-Market-New-Renew-NonRenew-by-ZIP-2020-2023.xlsx",
]

AGOL = "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/"
# name on disk -> (service/layer, fields to keep, include shapes?)
LAYERS = {
    "damage_2025": ("2025_Parcels_with_DINS_data/FeatureServer/5",
                    "SitusZIP,Fire_Name,DAMAGE_1,STRUCTURECATEGORY,UseType,YearBuilt1,"
                    "Roll_ImpValue,CENTER_LAT,CENTER_LON", False),
    "zip_codes": ("LA_County_ZIP_Codes/FeatureServer/0", "ZIPCODE", True),
    # "Archive" = the hazard maps in force BEFORE the 2025 fires (LRA map from 2011,
    # SRA map from 2007). Using the post-fire 2025 redraw would give the state hindsight.
    "fhsz_lra_pre2025": ("Archive_FHSZLRA/FeatureServer/2", "HAZ_CLASS", True),
    "fhsz_sra_pre2025": ("Archive_FHSZSRA/FeatureServer/3", "HAZ_CLASS", True),
    "perimeter_eaton": ("Palisades_and_Eaton_Dissolved_Fire_Perimeters_as_of_20250121/FeatureServer/0", "FIRE_NAME", True),
    "perimeter_palisades": ("Palisades_and_Eaton_Dissolved_Fire_Perimeters_as_of_20250121/FeatureServer/1", "FIRE_NAME", True),
}


def fetch_layer(path, fields, geometry):
    """ArcGIS returns at most ~2,000 features per request, so page with resultOffset."""
    feats, offset = [], 0
    while True:
        r = requests.get(AGOL + path + "/query", params={
            "where": "1=1", "outFields": fields, "returnGeometry": str(geometry).lower(),
            "outSR": 4326, "f": "geojson", "resultOffset": offset, "resultRecordCount": 2000,
            "orderByFields": "OBJECTID",
        }, timeout=120)
        r.raise_for_status()
        page = r.json().get("features", [])
        feats += page
        if len(page) < 2000:
            return {"type": "FeatureCollection", "features": feats}
        offset += len(page)


if __name__ == "__main__":
    for f in CDI_FILES:
        out = RAW / f
        if not out.exists():
            out.write_bytes(requests.get(CDI + f, timeout=120).content)
        print(f"{f}: {out.stat().st_size / 1e3:.0f} KB")
    # USPS place names for each ZIP code (used for labels and search on the page)
    names = requests.get(AGOL + "LACZipFeb2023/FeatureServer/0/query", params={
        "where": "1=1", "outFields": "ZIP,NAME", "returnGeometry": "false", "resultRecordCount": 2000, "f": "json"}, timeout=120)
    (RAW / "zip_names.json").write_text(names.text)
    print(f"zip_names: {len(names.json()['features'])} ZIP codes")
    for name, (path, fields, geometry) in LAYERS.items():
        fc = fetch_layer(path, fields, geometry)
        (RAW / f"{name}.geojson").write_text(json.dumps(fc))
        print(f"{name}: {len(fc['features']):,} features")
