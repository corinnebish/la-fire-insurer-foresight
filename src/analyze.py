"""Did insurers' pullback point at the ZIPs that burned, and did it beat the state hazard map?

With only 7 burned ZIPs a regression would be meaningless, so the tests are rankings:
where does each burned ZIP land when all usable LA County ZIPs are sorted by each warning
sign, and what share of destroyed homes sat in each sign's "top 10%"?
"""
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
t = pd.read_csv(ROOT / "data" / "processed" / "zip_table.csv", dtype={"zip": str}).set_index("zip")
t = t[~t.too_small]

SIGNALS = {
    "company_drop_2019_21": "Insurers: share of policies dropped by the company, 2019-2021",
    "company_drop_change": "Insurers: rise in company drops, 2015-17 to 2019-21",
    "overall_drop_2022_23": "Insurers: all non-renewals, 2022-2023",
    "very_high_hazard_share": "State map: share of land rated Very High hazard (pre-2025 map)",
}

# 1. Percentile rank of each burned ZIP under each signal (100 = flagged as the riskiest).
pct = pd.DataFrame({k: t[k].rank(pct=True) * 100 for k in SIGNALS})
burned = t[t.burned].sort_values("homes_destroyed", ascending=False)
print("Percentile rank of each burned ZIP (100 = most flagged):")
print(pct.loc[burned.index].round(0).join(burned.homes_destroyed).to_string(), "\n")

# 2. Share of all destroyed homes that sat in each signal's top 10% of ZIPs.
total = t.homes_destroyed.sum()
rows = []
for k, label in SIGNALS.items():
    top = pct[k] >= 90
    rows.append({"signal": label, "zips_flagged": int(top.sum()),
                 "share_of_destroyed_homes_caught": t.loc[top, "homes_destroyed"].sum() / total})
caught = pd.DataFrame(rows)
print(caught.round(3).to_string(index=False), "\n")

# 3. Did insurers mostly follow the state map? (rank correlation across ZIPs)
s = t[["very_high_hazard_share", "company_drop_2019_21"]].dropna()
rho, p = spearmanr(s.very_high_hazard_share, s.company_drop_2019_21)
print(f"Insurer drop rate vs state map: Spearman rho = {rho:.2f} (p = {p:.3g})")

# 4. Matched comparison: hillside ZIPs (>=10% Very High land) that did NOT burn.
hill = t[(t.very_high_hazard_share >= 0.10)]
grp = hill.groupby("burned")[["company_drop_2015_17", "company_drop_2019_21", "overall_drop_2022_23"]].median()
print("\nMedian drop rates, hillside ZIPs only (burned vs not):\n", (grp * 100).round(2).to_string())
print("hillside ZIPs:", hill.burned.value_counts().to_dict())

pct.loc[burned.index].join(burned[["homes_destroyed"]]).to_csv(ROOT / "data" / "processed" / "burned_percentiles.csv")
caught.to_csv(ROOT / "data" / "processed" / "signal_scorecard.csv", index=False)
