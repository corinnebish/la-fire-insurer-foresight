"""Export site/data.js for the interactive page.

Includes, for every usable LA County ZIP code: place name, yearly insurer drop rates
(2015-2021), homes destroyed, state hazard-map share and percentile ranks. ZIP shapes
for the 3D model are projected to California Albers (meters), simplified and re-centered.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW, SITE = ROOT / "data" / "processed", ROOT / "data" / "raw", ROOT / "site"
SITE.mkdir(exist_ok=True)

t = pd.read_csv(PROC / "zip_table.csv", dtype={"zip": str}).set_index("zip")
use = t[~t.too_small].copy()
years = pd.read_csv(PROC / "zip_years.csv", dtype={"zip": str})
cd = years[years.measure == "company_drop"]

names = {str(f["attributes"]["ZIP"]).zfill(5): f["attributes"]["NAME"].title()
         for f in json.loads((RAW / "zip_names.json").read_text())["features"]}
names.update({"90272": "Pacific Palisades", "91001": "Altadena", "91107": "East Pasadena",
              "91104": "Northeast Pasadena", "90290": "Topanga"})

# percentile ranks among usable ZIPs (100 = flagged as riskiest)
for col in ["company_drop_change", "very_high_hazard_share", "overall_drop_2022_23", "company_drop_2019_21"]:
    use["pct_" + col] = use[col].rank(pct=True) * 100


def pr(v):
    return None if pd.isna(v) else round(float(v))


def r(v, n=4):
    return None if pd.isna(v) else round(float(v), n)


series = {z: g.sort_values("year").rate.round(4).tolist() for z, g in cd.groupby("zip")}
yrs = sorted(cd.year.unique().tolist())
cd = cd.assign(drops=cd.rate * cd.up_for_renewal)
county = (cd.groupby("year").drops.sum() / cd.groupby("year").up_for_renewal.sum()).round(4).tolist()


def pooled(df, yrs_):
    g = df[df.year.isin(yrs_)]
    return g.drops.sum() / g.up_for_renewal.sum()


county_1517, county_1921 = pooled(cd, [2015, 2016, 2017]), pooled(cd, [2019, 2020, 2021])

out = {"years": yrs, "county": county, "zips": [], "shapes": [], "perimeters": []}
for z, row in use.iterrows():
    out["zips"].append({
        "zip": z, "name": names.get(z, "ZIP " + z), "destroyed": int(row.homes_destroyed),
        "d1517": r(row.company_drop_2015_17), "d1921": r(row.company_drop_2019_21),
        "change": r(row.company_drop_change), "d2223": r(row.overall_drop_2022_23),
        "hazard": r(row.very_high_hazard_share, 3),
        "pctChange": pr(row.pct_company_drop_change), "pctHazard": pr(row.pct_very_high_hazard_share),
        "pct2223": pr(row.pct_overall_drop_2022_23),
        "series": series.get(z, [])})

# headline statistics
s = use[["very_high_hazard_share", "company_drop_change"]].dropna()
rho = spearmanr(s.very_high_hazard_share, s.company_drop_change)[0]
total = use.homes_destroyed.sum()
caught = {k: float(use.loc[use["pct_" + k] >= 90, "homes_destroyed"].sum() / total)
          for k in ["company_drop_change", "very_high_hazard_share"]}
out["stats"] = {"destroyed": int(t.homes_destroyed.sum()), "zipsUsed": int(len(use)), "rho": round(float(rho), 2),
                "caughtInsurers": round(caught["company_drop_change"], 3), "caughtMap": round(caught["very_high_hazard_share"], 3),
                "county1517": round(county_1517, 4), "county1921": round(county_1921, 4)}

# 3D shapes: LA basin around the fires
zips = gpd.read_file(PROC / "zips.geojson").to_crs(3310)
perims = pd.concat([gpd.read_file(RAW / f"perimeter_{f}.geojson").to_crs(3310) for f in ("eaton", "palisades")])
box = perims.total_bounds
cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
zips = zips[zips.centroid.distance(gpd.points_from_xy([cx], [cy], crs=3310)[0]) < 60_000]


def rings(geom, tol=120):
    geom = geom.simplify(tol)
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return [[[round((x - cx) / 1000, 2), round((y - cy) / 1000, 2)] for x, y in p.exterior.coords]
            for p in polys if p.area > 200_000]


for _, z in zips.iterrows():
    row = t.loc[z.zip]
    out["shapes"].append({"zip": z.zip, "rings": rings(z.geometry), "destroyed": int(row.homes_destroyed),
                          "hazard": r(row.very_high_hazard_share, 3)})
for _, p in perims.iterrows():
    out["perimeters"].append(rings(p.geometry, 60))

(SITE / "data.js").write_text("window.FIRE_DATA = " + json.dumps(out, separators=(",", ":")) + ";")
print(f"{len(out['zips'])} ZIPs with data, {len(out['shapes'])} shapes, {(SITE / 'data.js').stat().st_size / 1e3:.0f} KB")
print(out["stats"])
