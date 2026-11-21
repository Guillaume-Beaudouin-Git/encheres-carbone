"""Question 2, demand: cover ratio, number of bidders and the price - mean bid spread, year by year.

Writes results/demand.json and figures/Q2_demand_by_year.png.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from eua_auctions import style
from eua_auctions.data import load
from eua_auctions.demand import add_spread, rank_correlation, yearly_demand

FIGURES, RESULTS = Path("figures"), Path("results")


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    style.apply()
    df, _ = load()
    yearly = yearly_demand(df)
    d = add_spread(df)
    outliers = d[d["mean_bid"] > 1.05 * d["price"]]

    results = {
        "yearly": {int(y): {k: round(float(v), 4) for k, v in r.items()} for y, r in yearly.iterrows()},
        "all_auctions": {
            "cover_median": round(float(df["cover"].median()), 4),
            "cover_min": round(float(df["cover"].min()), 4),
            "cover_max": round(float(df["cover"].max()), 4),
            "spread_median_pct": round(float(d["spread_pct"].median()), 4),
            "spearman_cover_spread": round(rank_correlation(df, "cover", "spread_pct"), 4),
            "spearman_cover_bidders": round(rank_correlation(df, "cover", "n_bidders"), 4),
        },
        "mean_bid_above_price_by_5pct": {
            "count": int(len(outliers)),
            "auctions": [{"date": str(r["date"].date()), "zone": r["zone"], "price": float(r["price"]),
                          "mean_bid": float(r["mean_bid"]), "max_bid": float(r["max_bid"])}
                         for _, r in outliers.iterrows()],
        },
    }
    (RESULTS / "demand.json").write_text(json.dumps(results, indent=2))

    # Figure: cover ratio per auction and its yearly median; bidders per year
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.6), sharex=True, gridspec_kw={"height_ratios": [1.5, 1]})
    mid_year = pd.to_datetime(yearly.index.astype(str) + "-07-01")
    ax1.scatter(df["date"], df["cover"], s=5, color=style.GREY, alpha=0.45, linewidths=0, label="one auction")
    ax1.fill_between(mid_year, yearly["cover_q25"], yearly["cover_q75"], color=style.BLUE, alpha=0.15, linewidth=0,
                     label="yearly interquartile range")
    ax1.plot(mid_year, yearly["cover_median"], color=style.BLUE, lw=2, marker="o", ms=5, label="yearly median")
    ax1.axhline(1, color=style.INK_2, lw=0.8, ls=":")
    ax1.text(df["date"].min(), 1.04, "cover = 1: below it the auction is cancelled", fontsize=8, color=style.INK_2,
             va="bottom")
    ax1.set_yscale("log")
    ax1.set_yticks([1, 1.5, 2, 3, 5, 10])
    ax1.set_yticklabels(["1", "1.5", "2", "3", "5", "10"])
    ax1.set_ylim(0.9, 15)
    ax1.set_ylabel("Cover ratio (bids / volume, log scale)")
    ax1.set_title("EUA auctions on EEX: cover ratio and bidders, 2013-2026")
    ax1.legend(loc="upper right", ncols=3, fontsize=8.5)

    ax2.plot(mid_year, yearly["bidders_mean"], color=style.BLUE, lw=2, marker="o", ms=5, label="bidders")
    ax2.plot(mid_year, yearly["successful_bidders_mean"], color=style.ORANGE, lw=2, marker="o", ms=5,
             label="successful bidders")
    for series, colour in [("bidders_mean", style.BLUE), ("successful_bidders_mean", style.ORANGE)]:
        ax2.text(mid_year[-1] + pd.Timedelta(days=60), yearly[series].iloc[-1],
                 f"{yearly[series].iloc[-1]:.1f}", va="center", fontsize=8.5, color=style.INK)
    ax2.set_ylim(0, yearly["bidders_mean"].max() * 1.2)
    ax2.set_ylabel("Mean number per auction")
    ax2.legend(loc="lower left", ncols=2, fontsize=8.5)
    ax2.text(0, -0.2, f"Source: EEX auction reports, {len(df):,} EUA auctions; 2026 up to 20 November.",
             transform=ax2.transAxes, fontsize=8, color=style.INK_2)
    fig.savefig(FIGURES / "Q2_demand_by_year.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(yearly.round(2).to_string())
    print(json.dumps(results["all_auctions"], indent=1))
    print(json.dumps(results["mean_bid_above_price_by_5pct"], indent=1))


if __name__ == "__main__":
    main()
