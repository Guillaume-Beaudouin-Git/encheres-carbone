import numpy as np
import pandas as pd
import pytest

from eua_auctions.cover_signal import (bucket, bucket_test, forward_change, sample, select_on_train,
                                       trailing_rank)


def _synthetic(seed=0):
    """Three auctions a week from 2013 to 2022: random-walk prices, random cover ratios."""
    dates = pd.date_range("2013-01-01", "2022-12-31", freq="W-MON")
    dates = dates.union(dates + pd.Timedelta(days=1)).union(dates + pd.Timedelta(days=3))
    rng = np.random.default_rng(seed)
    price = 20 * np.exp(np.cumsum(rng.normal(0, 0.02, len(dates))))
    cover = np.exp(rng.normal(0.7, 0.3, len(dates)))
    return pd.DataFrame({"date": dates, "price": price, "cover": cover})


def test_trailing_rank_by_hand():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 2.5, 2.0])
    r = trailing_rank(x, window=4)
    assert r.iloc[:4].isna().all()
    assert r.iloc[4] == pytest.approx(0.5)            # 2.5 is above 1 and 2 among [1, 2, 3, 4]
    assert r.iloc[5] == pytest.approx(0.125)          # 2.0 among [2, 3, 4, 2.5]: one tie, counts one half


def test_trailing_rank_does_not_look_ahead():
    x = pd.Series(np.arange(20, dtype=float))
    y = x.copy()
    y.iloc[12:] = -100.0                              # change everything from auction 12 on
    assert trailing_rank(x, 5).iloc[:12].equals(trailing_rank(y, 5).iloc[:12])


def test_forward_change_by_hand():
    p = pd.Series([10.0, 11.0, 12.1, 13.31])
    f1 = forward_change(p, k=1)
    assert f1.iloc[:3].tolist() == pytest.approx([100 * np.log(1.1)] * 3)
    assert np.isnan(f1.iloc[3])
    assert forward_change(p, k=2).iloc[0] == pytest.approx(100 * np.log(1.21))
    assert forward_change(p, k=1, skip=1).iloc[0] == pytest.approx(100 * np.log(12.1 / 11.0))  # from t+1


def test_buckets_and_contrast_by_hand():
    rank = pd.Series([0.05, 0.5, 0.95, 0.1, 0.9, 0.5])
    assert bucket(rank, 0.1).tolist() == ["low", "mid", "high", "low", "high", "mid"]
    s = pd.DataFrame({"bucket": bucket(rank, 0.1), "fwd": [-1.0, 0.0, 1.0, -1.0, 1.0, 0.0]})
    r = bucket_test(s, lags=1)
    assert r["mean_low"] == pytest.approx(-1.0) and r["mean_high"] == pytest.approx(1.0)
    assert r["high_minus_low"] == pytest.approx(2.0)


def test_training_sample_never_reaches_the_test_years():
    df = _synthetic()
    for k in (1, 5, 10):
        s = sample(df, "2014-01-01", "2020-12-31", k, 0.2)
        assert s["date"].min() >= pd.Timestamp("2014-01-01")
        assert s["target_date"].max() <= pd.Timestamp("2020-12-31")
        # the last k auctions of 2020 have their target in 2021: they are left out
        in_2020 = df[(df["date"] >= "2014-01-01") & (df["date"] <= "2020-12-31")]
        assert len(s) == len(in_2020) - k


def test_choice_ignores_the_test_years():
    df = _synthetic()
    table_a, chosen_a = select_on_train(df)
    other = df.copy()
    future = other["date"] >= "2021-01-01"
    rng = np.random.default_rng(1)
    other.loc[future, "price"] = rng.uniform(1, 500, future.sum())    # scramble prices and covers after 2020
    other.loc[future, "cover"] = rng.uniform(1, 10, future.sum())
    table_b, chosen_b = select_on_train(other)
    assert chosen_a == chosen_b
    pd.testing.assert_frame_equal(table_a, table_b)
