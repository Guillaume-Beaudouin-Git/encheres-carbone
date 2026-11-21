"""Question 2, demand: what the auction results say about bidders, year by year.

- Cover ratio = total volume bid / volume offered. Above 1 the auction is oversubscribed; below 1 it is cancelled.
- Bidders: the number of participants that bid, and the number that won some allowances.
- Spread = (clearing price - mean bid price) / clearing price, in %. Bids above the clearing price are filled and
  bids below it are rejected, so a mean bid well below the clearing price means many bids far below it: a wider
  dispersion of bidders' prices. EEX reports the mean of all bids; a single erroneous bid (one maximum bid of
  7,075 EUR/t on 11 June 2024) moves it, so the yearly figure is a median over auctions.
"""
from __future__ import annotations

import pandas as pd


def add_spread(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["spread_pct"] = 100 * (out["price"] - out["mean_bid"]) / out["price"]
    return out


def yearly_demand(df: pd.DataFrame) -> pd.DataFrame:
    d = add_spread(df)
    g = d.groupby("year")
    return pd.DataFrame({
        "auctions": g.size(),
        "cover_median": g["cover"].median(),
        "cover_q25": g["cover"].quantile(0.25),
        "cover_q75": g["cover"].quantile(0.75),
        "share_cover_below_1_5_pct": 100 * g["cover"].apply(lambda c: (c < 1.5).mean()),
        "bidders_mean": g["n_bidders"].mean(),
        "successful_bidders_mean": g["n_successful_bidders"].mean(),
        "spread_median_pct": g["spread_pct"].median(),
    })


def rank_correlation(df: pd.DataFrame, a: str, b: str) -> float:
    """Spearman rank correlation between two columns, auction by auction."""
    d = add_spread(df)
    return float(d[a].rank().corr(d[b].rank()))
