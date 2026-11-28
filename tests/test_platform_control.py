"""The post hoc platform control of question 3 on hand-built cases."""
import numpy as np
import pandas as pd
import pytest

from eua_auctions.cover_signal import bucket_test
from eua_auctions.platform_control import leave_one_year_out, platform_test


def _sample(n=400, signal=1.0, german_gap=-3.0, seed=0):
    """Forward change = signal after high cover + a gap after German auctions + small noise; German auctions are
    over-represented among high-cover auctions, as on 2021-2026."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-04", periods=n, freq="D")
    bucket = np.array(["mid"] * n, dtype=object)
    bucket[::10], bucket[5::10] = "high", "low"
    zone = np.where(rng.random(n) < 0.2, "DE", "EU")
    zone[::10] = np.where(rng.random(len(zone[::10])) < 0.7, "DE", "EU")
    fwd = signal * (bucket == "high") + german_gap * (zone == "DE") + rng.normal(0, 0.1, n)
    return pd.DataFrame({"date": dates, "bucket": bucket, "zone": zone, "fwd": fwd})


def test_the_control_recovers_the_signal_that_the_platform_gap_hides():
    s = _sample()
    raw = bucket_test(s, 2)
    controlled = platform_test(s, 2)
    assert raw["high_minus_low"] < 0.0                    # the German gap swamps the signal without the control
    assert controlled["high_minus_low"] == pytest.approx(1.0, abs=0.05)
    assert controlled["platforms"]["DE"]["coef"] == pytest.approx(-3.0, abs=0.05)
    assert controlled["n_base_platform"] + controlled["platforms"]["DE"]["n"] == len(s)
    lo, hi = controlled["ci95"]
    assert lo < controlled["high_minus_low"] < hi


def test_without_platform_differences_the_control_changes_nothing():
    s = _sample(german_gap=0.0)
    s["zone"] = "EU"                                      # a single platform: no dummy at all
    assert platform_test(s, 2)["high_minus_low"] == pytest.approx(bucket_test(s, 2)["high_minus_low"])
    assert platform_test(s, 2)["platforms"] == {}


def test_leave_one_year_out_drops_exactly_that_year():
    s = _sample(n=800)
    out = leave_one_year_out(s, 2)
    years = s["date"].dt.year
    assert sorted(out) == [str(y) for y in sorted(years.unique())]
    for y, r in out.items():
        assert r["n_left_out"] == int((years == int(y)).sum())
        assert r["without_year"]["n"] == len(s) - r["n_left_out"]
