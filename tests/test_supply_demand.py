import pandas as pd
import pytest

from eua_auctions.demand import add_spread, yearly_demand
from eua_auctions.supply import august_vs_july, monthly_volume


def _auctions(dates, volumes, **extra):
    d = pd.DataFrame({"date": pd.to_datetime(dates), "volume": volumes, **extra})
    d["year"] = d["date"].dt.year
    return d


def test_monthly_volume_sums_and_fills_empty_months():
    df = _auctions(["2020-01-06", "2020-01-07", "2020-03-02"], [2e6, 3e6, 4e6])
    m = monthly_volume(df)
    assert m.tolist() == pytest.approx([5.0, 0.0, 4.0])  # Mt; February has no auction
    assert m.index[1] == pd.Timestamp("2020-02-01")


def test_august_halved():
    # July: 4 auctions of 3 Mt; August: 4 auctions of 1.5 Mt
    df = _auctions(["2019-07-01", "2019-07-02", "2019-07-04", "2019-07-05",
                    "2019-08-05", "2019-08-06", "2019-08-08", "2019-08-09"], [3e6] * 4 + [1.5e6] * 4)
    a = august_vs_july(df)
    assert a.loc[2019, "ratio_per_auction"] == pytest.approx(0.5)
    assert a.loc[2019, "ratio_total"] == pytest.approx(0.5)
    assert a.loc[2019, "july_mt"] == pytest.approx(12.0)


def test_spread_and_yearly_medians():
    df = _auctions(["2021-01-04", "2021-01-05", "2021-01-07"], [1e6] * 3,
                   price=[50.0, 50.0, 40.0], mean_bid=[49.0, 50.0, 41.0], cover=[2.0, 1.5, 1.2],
                   n_bidders=[20, 22, 24], n_successful_bidders=[10, 12, 14])
    assert add_spread(df)["spread_pct"].tolist() == pytest.approx([2.0, 0.0, -2.5])
    y = yearly_demand(df).loc[2021]
    assert y["cover_median"] == pytest.approx(1.5)
    assert y["share_cover_below_1_5_pct"] == pytest.approx(100 / 3)
    assert y["bidders_mean"] == pytest.approx(22.0)
    assert y["spread_median_pct"] == pytest.approx(0.0)
