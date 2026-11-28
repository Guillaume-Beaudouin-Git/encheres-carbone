"""Post hoc check on question 3, added on 28 November 2026: the chosen test with a control for the platform.

Not part of the design. `cover_signal.py`, committed before the results, is unchanged; this check was chosen after
all results had been seen. The page's own limitations say why it is the first one a reader would try: on
2021-2026 most high-cover auctions are German, and a German auction does not clear at the same level as the next
auction. One test is added: the chosen variant, the same target and the same Newey-West errors, with one dummy for
the platform of auction t (the common platform is the base). Its fragility is reported with it: the same test
leaving out one year of auctions t at a time, and on the training years. The 9 variants are also run with the
control on the test years, for transparency only, as in `cover_signal.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

BASE_PLATFORM = "EU"


def platform_test(s: pd.DataFrame, lags: int) -> dict:
    """OLS of the forward change on a constant, the low and high dummies and one dummy per platform other than the
    base, with Newey-West errors; the contrast high - low and the platform coefficients.

    `s` is a sample from `cover_signal.sample` with a `zone` column (the platform of auction t). Rows are taken as
    consecutive, as in `cover_signal.bucket_test`, even when a year has been left out."""
    zones = sorted(z for z in s["zone"].unique() if z != BASE_PLATFORM)
    cols = {"const": np.ones(len(s)), "low": (s["bucket"] == "low").to_numpy(float),
            "high": (s["bucket"] == "high").to_numpy(float)}
    for z in zones:
        cols[f"zone_{z}"] = (s["zone"] == z).to_numpy(float)
    X = pd.DataFrame(cols)
    fit = sm.OLS(s["fwd"].to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    r = np.zeros(X.shape[1])
    r[1], r[2] = -1.0, 1.0
    c = fit.t_test(r[None, :])
    effect, se = float(c.effect[0]), float(np.squeeze(c.sd))
    return {
        "n": int(len(s)), "n_low": int((s["bucket"] == "low").sum()), "n_high": int((s["bucket"] == "high").sum()),
        "high_minus_low": effect, "se_hac": se, "t_hac": float(np.squeeze(c.tvalue)),
        "p_hac": float(np.squeeze(c.pvalue)), "ci95": [effect - 1.96 * se, effect + 1.96 * se],
        "platforms": {z: {"n": int((s["zone"] == z).sum()), "coef": float(fit.params[f"zone_{z}"]),
                          "t_hac": float(fit.tvalues[f"zone_{z}"])} for z in zones},
        "n_base_platform": int((s["zone"] == BASE_PLATFORM).sum()),
    }


def leave_one_year_out(s: pd.DataFrame, lags: int) -> dict:
    """The platform test without the auctions t of each year in turn, and the raw high - low of that year alone."""
    year = s["date"].dt.year
    out = {}
    for y in sorted(year.unique()):
        g = s[year == y]
        r = platform_test(s[year != y].reset_index(drop=True), lags)
        out[str(int(y))] = {"n_left_out": int(len(g)), "n_high_year": int((g["bucket"] == "high").sum()),
                            "n_low_year": int((g["bucket"] == "low").sum()),
                            "raw_high_minus_low_year": float(g.loc[g["bucket"] == "high", "fwd"].mean()
                                                             - g.loc[g["bucket"] == "low", "fwd"].mean()),
                            "without_year": {k: r[k] for k in ("n", "high_minus_low", "se_hac", "t_hac", "p_hac")}}
    return out
