"""Question 1, supply: how much is auctioned on EEX, month by month.

Everything here is a sum of the `volume` column of the cleaned auctions. Nothing is inferred about the Market
Stability Reserve: the files give the volume each auction offered, not what was withheld from it.
"""
from __future__ import annotations

import pandas as pd


def monthly_volume(df: pd.DataFrame) -> pd.Series:
    """Volume auctioned per calendar month, in million tonnes (Mt), with 0 for a month without any auction."""
    s = df.set_index("date")["volume"].resample("MS").sum() / 1e6
    return s.rename("volume_mt")


def annual_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Per year: number of auctions, total volume (Mt), mean volume per auction (Mt), first and last auction."""
    g = df.groupby("year")
    return pd.DataFrame({
        "auctions": g.size(),
        "volume_mt": g["volume"].sum() / 1e6,
        "mean_volume_per_auction_mt": g["volume"].mean() / 1e6,
        "first_auction": g["date"].min().dt.strftime("%Y-%m-%d"),
        "last_auction": g["date"].max().dt.strftime("%Y-%m-%d"),
    })


def august_vs_july(df: pd.DataFrame) -> pd.DataFrame:
    """August against July of the same year: total volume, auctions and volume per auction.

    July is the comparison month because it is the month just before, in the same summer, with about as many
    auction days."""
    rows = []
    for year, d in df.groupby("year"):
        jul, aug = d[d["date"].dt.month == 7], d[d["date"].dt.month == 8]
        if jul.empty or aug.empty:
            continue
        rows.append({
            "year": int(year),
            "july_mt": jul["volume"].sum() / 1e6, "august_mt": aug["volume"].sum() / 1e6,
            "july_auctions": len(jul), "august_auctions": len(aug),
            "ratio_total": aug["volume"].sum() / jul["volume"].sum(),
            "ratio_per_auction": aug["volume"].mean() / jul["volume"].mean(),
        })
    return pd.DataFrame(rows).set_index("year")


def change(annual: pd.DataFrame, before: int, after: int) -> dict:
    """Change in total volume and in volume per auction from one full year to another."""
    a, b = annual.loc[before], annual.loc[after]
    return {
        "from": before, "to": after,
        "volume_mt": [float(a["volume_mt"]), float(b["volume_mt"])],
        "change_total_pct": 100 * (b["volume_mt"] / a["volume_mt"] - 1),
        "volume_per_auction_mt": [float(a["mean_volume_per_auction_mt"]), float(b["mean_volume_per_auction_mt"])],
        "change_per_auction_pct": 100 * (b["mean_volume_per_auction_mt"] / a["mean_volume_per_auction_mt"] - 1),
    }
