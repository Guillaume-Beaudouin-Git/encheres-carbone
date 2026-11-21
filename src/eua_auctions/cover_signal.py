"""Question 3: does a low or a high cover ratio announce the change in the clearing price over the next auctions?

Design, fixed before the 2021-2026 results were computed:

- Series: every cleaned EUA auction, all platforms (EU, DE, PL, XI), in time order. Auction t is "the t-th
  auction"; k auctions ahead is a count of auctions, not of days.
- Signal at auction t: the percentile rank of its cover ratio among the previous `WINDOW` = 60 auctions (about
  three to four months). The cover ratio falls from a median of 5.2 in 2014 to 1.8 in 2020, inside the training
  years themselves, so a fixed threshold on the raw ratio would mostly sort auctions by year. The rank compares
  an auction with its recent past only. The window is set once and not tuned.
- Low cover: rank <= q. High cover: rank >= 1 - q. The rest is "mid".
- Target: the forward change 100 * ln(P[t+k] / P[t]) of the clearing price, in %. The cover ratio and the price of
  auction t are published together after the auction closes, so the signal is known at P[t].
- Training years 2014-2020: the 3 x 3 variants (k in 1, 5, 10; q in 0.1, 0.2, 0.3) are estimated, and the one with
  the largest |t-statistic| of (mean after high - mean after low) is chosen. A training row is kept only if
  auction t+k also falls in 2020 or before: no price from the test years enters the training sample.
- Test years 2021-2026: the chosen variant is applied once. Its forecast (the training mean of the forward change
  in each bucket) is compared with two naive references, no change and the training mean of all auctions.
- Inference: Newey-West (HAC) standard errors with 2k lags, because forward changes over k auctions overlap and
  the k = 1 changes need not be independent either.
- One robustness check on the chosen variant: the forward change measured from auction t+1 to t+1+k, which leaves
  out the clearing price of the signal auction itself.

That makes 10 variants in total (9 on the training grid, 1 robustness check). The 9 are also reported on the test
years for transparency, but only the chosen one is "the test".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

WINDOW = 60
HORIZONS = (1, 5, 10)
QUANTILES = (0.1, 0.2, 0.3)
TRAIN = ("2014-01-01", "2020-12-31")
TEST = ("2021-01-01", "2026-11-20")


def lags_for(k: int) -> int:
    return 2 * k


def trailing_rank(x: pd.Series, window: int = WINDOW) -> pd.Series:
    """Share of the previous `window` values below x[t] (ties count one half); NaN for the first `window` values.

    Only x[t - window], ..., x[t - 1] and x[t] enter the rank at t: nothing that comes later."""
    v = x.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    for t in range(window, len(v)):
        past = v[t - window:t]
        out[t] = ((past < v[t]).sum() + 0.5 * (past == v[t]).sum()) / window
    return pd.Series(out, index=x.index, name="rank")


def forward_change(price: pd.Series, k: int, skip: int = 0) -> pd.Series:
    """100 * ln(P[t + skip + k] / P[t + skip]), in %; NaN where the series ends too early."""
    logp = np.log(price.to_numpy(dtype=float))
    n, out = len(logp), np.full(len(logp), np.nan)
    for t in range(n - skip - k):
        out[t] = 100 * (logp[t + skip + k] - logp[t + skip])
    return pd.Series(out, index=price.index, name="fwd")


def bucket(rank: pd.Series, q: float) -> pd.Series:
    b = pd.Series("mid", index=rank.index)
    b[rank <= q] = "low"
    b[rank >= 1 - q] = "high"
    b[rank.isna()] = None
    return b


def sample(df: pd.DataFrame, start: str, end: str, k: int, q: float, skip: int = 0,
           window: int = WINDOW) -> pd.DataFrame:
    """Auctions t with date in [start, end] whose target auction t + skip + k is also dated <= end.

    `df` must be sorted by time and cover the whole history: the rank at the first auctions of the period uses
    the auctions just before it, which are in the past."""
    d = df.reset_index(drop=True)
    rank = trailing_rank(d["cover"], window)
    fwd = forward_change(d["price"], k, skip)
    pos = np.arange(len(d))
    target_pos = np.minimum(pos + skip + k, len(d) - 1)
    target_date = d["date"].to_numpy()[target_pos]
    keep = ((d["date"] >= pd.Timestamp(start)) & (d["date"] <= pd.Timestamp(end))
            & (pos + skip + k < len(d)) & (target_date <= np.datetime64(pd.Timestamp(end)))
            & rank.notna() & fwd.notna())
    out = pd.DataFrame({"date": d["date"], "target_date": target_date, "cover": d["cover"], "rank": rank,
                        "bucket": bucket(rank, q), "fwd": fwd})
    return out[keep.to_numpy()].reset_index(drop=True)


def bucket_test(s: pd.DataFrame, lags: int) -> dict:
    """Mean forward change after low, mid and high cover, and the HAC test of (high - low) = 0.

    Regression of the forward change on a constant and two dummies (low, high), mid being the base; the
    contrast high - low and its Newey-West standard error come from the same fit, on consecutive auctions."""
    y = s["fwd"].to_numpy()
    X = np.column_stack([np.ones(len(s)), (s["bucket"] == "low").to_numpy(float), (s["bucket"] == "high").to_numpy(float)])
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    contrast = fit.t_test(np.array([[0.0, -1.0, 1.0]]))
    means = s.groupby("bucket")["fwd"].mean()
    counts = s["bucket"].value_counts()
    return {
        "n": int(len(s)),
        "n_low": int(counts.get("low", 0)), "n_mid": int(counts.get("mid", 0)), "n_high": int(counts.get("high", 0)),
        "mean_all": float(y.mean()),
        "mean_low": float(means.get("low", np.nan)), "mean_mid": float(means.get("mid", np.nan)),
        "mean_high": float(means.get("high", np.nan)),
        "high_minus_low": float(contrast.effect[0]),
        "se_hac": float(np.squeeze(contrast.sd)),
        "t_hac": float(np.squeeze(contrast.tvalue)),
        "p_hac": float(np.squeeze(contrast.pvalue)),
        "ci95": [float(contrast.effect[0] - 1.96 * np.squeeze(contrast.sd)),
                 float(contrast.effect[0] + 1.96 * np.squeeze(contrast.sd))],
    }


def grid(df: pd.DataFrame, start: str, end: str, horizons=HORIZONS, quantiles=QUANTILES) -> pd.DataFrame:
    rows = []
    for k in horizons:
        for q in quantiles:
            r = bucket_test(sample(df, start, end, k, q), lags_for(k))
            rows.append({"k": k, "q": q, **{key: v for key, v in r.items() if key != "ci95"}})
    return pd.DataFrame(rows)


def select_on_train(df: pd.DataFrame, train=TRAIN) -> tuple[pd.DataFrame, dict]:
    """Evaluate the grid on the training years only and return it with the chosen (k, q)."""
    table = grid(df, *train)
    best = table.loc[table["t_hac"].abs().idxmax()]
    return table, {"k": int(best["k"]), "q": float(best["q"])}


def forecast_comparison(df: pd.DataFrame, k: int, q: float, train=TRAIN, test=TEST, skip: int = 0) -> dict:
    """Out-of-sample forecast of the forward change on the test years, against two naive references.

    Model: the training mean of the forward change in the auction's bucket (low / mid / high).
    References: no change (0) and the training mean of all auctions. R2_oos = 1 - SSE_model / SSE_reference; the
    Diebold-Mariano statistic is the HAC t-statistic of the mean of (e_ref^2 - e_model^2), positive if the model
    is better."""
    tr = sample(df, *train, k, q, skip)
    te = sample(df, *test, k, q, skip)
    bucket_means = tr.groupby("bucket")["fwd"].mean()
    pred = te["bucket"].map(bucket_means).to_numpy()
    y = te["fwd"].to_numpy()
    out = {"train_bucket_means": {b: float(v) for b, v in bucket_means.items()}, "n_test": int(len(te))}
    for name, ref in {"no_change": np.zeros(len(y)), "train_mean": np.full(len(y), tr["fwd"].mean())}.items():
        e_model, e_ref = y - pred, y - ref
        d = e_ref ** 2 - e_model ** 2
        dm = sm.OLS(d, np.ones(len(d))).fit(cov_type="HAC", cov_kwds={"maxlags": lags_for(k)})
        out[name] = {
            "rmse_model": float(np.sqrt(np.mean(e_model ** 2))),
            "rmse_reference": float(np.sqrt(np.mean(e_ref ** 2))),
            "r2_oos_pct": float(100 * (1 - (e_model ** 2).sum() / (e_ref ** 2).sum())),
            "dm_t_hac": float(dm.tvalues[0]), "dm_p_hac": float(dm.pvalues[0]),
        }
    return out
