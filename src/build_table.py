"""Clean every source and combine them into one row per LA County ZIP code.

Output: data/processed/zip_table.csv, plus yearly drop rates in zip_years.csv
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
EQUAL_AREA = 3310  # California Albers: a map projection in meters, so areas are accurate


def load_insurance():
    """Return two SEPARATE yearly tables.

    The 2015-2021 file splits dropped policies into "insurer-initiated" (the company
    dropped you) and "insured-initiated" (you left). The 2020-2023 file has a single
    "Non-Renewed" column that matches neither in the years both files cover, so the
    state changed its definition. Stitching them together would create a fake jump.
    """
    old = pd.read_excel(RAW / "Residential-Property-Voluntary-Market-New-Renew-NonRenew-by-ZIP-2015-2021.xlsx")
    new = pd.read_excel(RAW / "Residential-Insurance-Voluntary-Market-New-Renew-NonRenew-by-ZIP-2020-2023.xlsx")
    for df in (old, new):
        df["County"] = df["County"].astype(str).str.strip()  # names carry trailing spaces
        df["zip"] = df["ZIP Code"].astype(int).astype(str).str.zfill(5)
    old = old[old.County == "Los Angeles"].rename(columns={
        "Year": "year", "Renewed": "renewed",
        "Insured-Initiated Nonrenewed": "left_by_owner",
        "Insurer-Initiated Nonrenewed": "dropped_by_company"})
    new = new[new.County == "Los Angeles"].rename(columns={
        "Year": "year", "Renewed": "renewed", "Non-Renewed": "non_renewed"})
    old["up_for_renewal"] = old.renewed + old.left_by_owner + old.dropped_by_company
    new["up_for_renewal"] = new.renewed + new.non_renewed
    return old, new


def period_rate(df, numerator, years):
    """Pooled rate over several years: sum of drops / sum of policies (steadier than averaging)."""
    g = df[df.year.isin(years)].groupby("zip")[[numerator, "up_for_renewal"]].sum()
    return g[numerator] / g.up_for_renewal


def load_damage(zips):
    d = gpd.read_file(RAW / "damage_2025.geojson")
    # Only homes: home insurance covers residences. ~2,300 parcels have a blank ZIP,
    # so assign every parcel a ZIP from its map location instead of the typed address.
    d = d[d.UseType == "Residential"].dropna(subset=["CENTER_LAT", "CENTER_LON"])
    pts = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.CENTER_LON, d.CENTER_LAT), crs=4326)
    pts = gpd.sjoin(pts, zips[["zip", "geometry"]], predicate="within", how="left")
    pts["destroyed"] = pts.DAMAGE_1.str.startswith("Destroyed", na=False)
    return pts.groupby("zip").agg(homes_inspected=("destroyed", "size"),
                                  homes_destroyed=("destroyed", "sum"))


def very_high_share(zips):
    """Share of each ZIP's land the PRE-2025 state map rated 'Very High' fire hazard."""
    fh = pd.concat([gpd.read_file(RAW / f"fhsz_{k}_pre2025.geojson") for k in ("lra", "sra")])
    vh = fh[fh.HAZ_CLASS == "Very High"].to_crs(EQUAL_AREA)
    vh = gpd.GeoDataFrame(geometry=[vh.geometry.buffer(0).union_all()], crs=EQUAL_AREA)
    z = zips.to_crs(EQUAL_AREA)
    inter = gpd.overlay(z[["zip", "geometry"]], vh, how="intersection")
    inter["vh_area"] = inter.area
    share = inter.groupby("zip").vh_area.sum() / z.set_index("zip").area
    return share.reindex(z.zip).fillna(0).clip(0, 1)


if __name__ == "__main__":
    zips = gpd.read_file(RAW / "zip_codes.geojson").rename(columns={"ZIPCODE": "zip"})
    zips["zip"] = zips.zip.astype(str).str[:5]
    zips = zips.dissolve("zip").reset_index()  # a few ZIPs come in several pieces

    old, new = load_insurance()
    t = pd.DataFrame(index=sorted(set(old.zip) & set(zips.zip)))
    t.index.name = "zip"
    t["policies_2021"] = old[old.year == 2021].set_index("zip").up_for_renewal
    t["company_drop_2015_17"] = period_rate(old, "dropped_by_company", [2015, 2016, 2017])
    t["company_drop_2019_21"] = period_rate(old, "dropped_by_company", [2019, 2020, 2021])
    t["company_drop_change"] = t.company_drop_2019_21 - t.company_drop_2015_17
    t["overall_drop_2022_23"] = period_rate(new, "non_renewed", [2022, 2023])
    t = t.join(load_damage(zips)).fillna({"homes_inspected": 0, "homes_destroyed": 0})
    t["pct_destroyed"] = t.homes_destroyed / t.policies_2021
    t["very_high_hazard_share"] = very_high_share(zips)
    # Fewer than 100 policies a year means 3 drops can look like a 3% swing: too noisy.
    t["too_small"] = t.policies_2021 < 100
    t["burned"] = t.homes_destroyed >= 20  # real destruction, not one stray parcel
    t.reset_index().to_csv(OUT / "zip_table.csv", index=False)

    yearly = pd.concat([
        old.assign(rate=old.dropped_by_company / old.up_for_renewal, measure="company_drop")[["zip", "year", "rate", "up_for_renewal", "measure"]],
        new.assign(rate=new.non_renewed / new.up_for_renewal, measure="overall_drop")[["zip", "year", "rate", "up_for_renewal", "measure"]],
    ])
    yearly.to_csv(OUT / "zip_years.csv", index=False)
    zips[zips.zip.isin(t.index)][["zip", "geometry"]].to_file(OUT / "zips.geojson", driver="GeoJSON")

    print(f"{len(t)} ZIPs, {(~t.too_small).sum()} large enough to use, {t.burned.sum()} burned")
    print(t[t.burned].sort_values("homes_destroyed", ascending=False)
          [["homes_destroyed", "pct_destroyed", "company_drop_2015_17", "company_drop_2019_21", "very_high_hazard_share"]].round(3).to_string())
