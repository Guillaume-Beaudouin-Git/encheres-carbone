"""Question 1, supply: volumes auctioned per month, 2013-2026.

Writes results/supply.json and figures/Q1_monthly_volume.png.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd

from eua_auctions import style
from eua_auctions.data import END, load
from eua_auctions.supply import annual_volume, august_vs_july, august_vs_july_by_platform, change, monthly_volume

FIGURES, RESULTS = Path("figures"), Path("results")


def _rounded(d: dict) -> dict:
    return {k: (round(float(v), 4) if isinstance(v, float) else [round(x, 4) for x in v] if isinstance(v, list) else v)
            for k, v in d.items()}


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    style.apply()
    df, _ = load()
    monthly = monthly_volume(df)
    annual = annual_volume(df)
    aug = august_vs_july(df)
    by_platform = august_vs_july_by_platform(df)
    full_years = annual.loc[2013:2025]

    results = {
        "window": [str(df["date"].min().date()), END],
        "note": "2026 is a partial year: auctions up to the end of the window.",
        "annual": {int(y): {k: (round(float(v), 4) if not isinstance(v, str) else v) for k, v in r.items()}
                   for y, r in annual.iterrows()},
        # all platforms pooled, per year (kept for reference; the README uses the per-platform ratio below)
        "august_vs_july_pooled": {int(y): {k: round(float(v), 4) for k, v in r.items()} for y, r in aug.iterrows()},
        # per platform: median August auction / median July auction
        "august_vs_july_by_platform": [{k: (round(float(v), 4) if k == "ratio_median_auction" else v)
                                        for k, v in r.items()} for r in by_platform.to_dict(orient="records")],
        "august_vs_july_by_platform_summary": {
            f"{a}-{b}": {
                "platform_years": int(len(p)),
                "ratio_rounded_counts": {f"{r:.2f}": int(n) for r, n in p["ratio_median_auction"].round(2).value_counts().sort_index().items()},
                "exceptions_to_0_50" if b <= 2023 else "exceptions_to_1_00": [
                    {"year": int(r.year), "zone": r.zone, "ratio": round(float(r.ratio_median_auction), 4),
                     "july_auctions": int(r.july_auctions), "august_auctions": int(r.august_auctions)}
                    for r in p.itertuples() if round(r.ratio_median_auction, 2) != (0.5 if b <= 2023 else 1.0)],
            } for a, b in [(2013, 2023), (2024, 2026)]
            for p in [by_platform[(by_platform["year"] >= a) & (by_platform["year"] <= b)]]
        },
        **{f"change_{a}_{b}": _rounded(change(annual, a, b)) for a, b in [(2013, 2014), (2018, 2019), (2020, 2021)]},
        "full_years_2013_2025": {
            "largest_mt": [int(full_years["volume_mt"].idxmax()), round(float(full_years["volume_mt"].max()), 4)],
            "smallest_mt": [int(full_years["volume_mt"].idxmin()), round(float(full_years["volume_mt"].min()), 4)],
        },
        "monthly_mt": {d.strftime("%Y-%m"): round(float(v), 4) for d, v in monthly.items()},
    }
    (RESULTS / "supply.json").write_text(json.dumps(results, indent=2))

    # Figure: one bar per month, August in orange
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colours = [style.ORANGE if d.month == 8 else style.BLUE for d in monthly.index]
    ax.bar(monthly.index, monthly.values, width=24, color=colours, linewidth=0)
    top = monthly.max()
    for when, label, side in [("2019-01-01", "Market Stability Reserve\nstarts operating (2019)", "right"),
                              ("2021-01-01", "Phase 4 starts;\nfirst auction 29 Jan 2021", "left")]:
        x = pd.Timestamp(when)
        ax.axvline(x, color=style.INK_2, lw=0.9, ls="--")
        shift = pd.Timedelta(days=-45 if side == "right" else 45)
        ax.text(x + shift, top * 1.21, label, va="top", ha=side, fontsize=8.5, color=style.INK_2)
    ax.legend(handles=[Patch(color=style.BLUE, label="month"), Patch(color=style.ORANGE, label="August")],
              loc="upper right", ncols=2)
    ax.set_ylabel("Volume auctioned on EEX (Mt of EUA)")
    ax.set_ylim(0, top * 1.24)
    ax.set_title("EUA primary auctions on EEX: volume per month, Jan 2013 - Nov 2026")
    ax.text(0, -0.17, "Source: EEX auction reports. General allowances only (no aviation auctions); since January 2025, "
            "aviation allowances are sold\nwithin the EUA auctions. "
            f"November 2026: auctions up to {pd.Timestamp(END).day} November.",
            transform=ax.transAxes, fontsize=8, color=style.INK_2)
    fig.savefig(FIGURES / "Q1_monthly_volume.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(annual.round(2).to_string())
    print(by_platform.round(4).to_string())
    print(json.dumps({k: results[k] for k in ["august_vs_july_by_platform_summary", "change_2013_2014", "change_2018_2019",
                                               "change_2020_2021", "full_years_2013_2025"]}, indent=1))


if __name__ == "__main__":
    main()
