import numpy as np
import pandas as pd
import pytest

from eua_auctions.data import canonical_column, clean, find_header_row, tidy_sheet

HEADER_2013 = ["Date", "Time", "Auction Name", "Contract", "Auction Price €/tCO2", "Minimum Bid €/tCO2",
               "Maximum Bid €/tCO2", "Mean €/tCO2", "Median €/tCO2", "Auction Volume tCO2", "Total Amount of Bids ",
               "Cover Ratio", "Total Number of Bidders", "Number of Successful Bidders", "Total Revenue €", "Country",
               "Auction Details"]


def _row(date, contract, price, volume, bids, name="EU", time="11:00:00"):
    return [date, time, name, contract, price, price - 1, price + 1, price - 0.1, price, volume, bids,
            round(bids / volume, 2), 20, 15, price * volume, name, None]


def _sheet_2013_layout(rows):
    """A sheet as pandas reads it without header: a title line, a group line, then the header on line 3."""
    title = ["EEX Emissionsmarkt / EUA Auction"] + [None] * 16
    groups = [None, None, None, None, "Prices", None, None, None, None, "Volumes"] + [None] * 7
    return pd.DataFrame([title, groups, HEADER_2013] + rows)


def test_canonical_column_spellings():
    # the same quantity is spelt differently across the years
    assert canonical_column("Minimal Price €/tCO2") == "min_bid"          # 2012
    assert canonical_column("Minimum Bid EUR/tCO2") == "min_bid"          # 2016
    assert canonical_column("Auction Price EUR/tCO2") == "price"
    assert canonical_column("Total Amount of Bids ") == "bid_volume"      # trailing space in 2012-2015
    assert canonical_column("Number of Succesful  Bidders") == "n_successful_bidders"  # 2016 typo
    assert canonical_column("Zone") == "zone" and canonical_column("Country") == "zone"  # 2026 vs before
    assert canonical_column("Auction Time") == "time"
    assert canonical_column("Germany (DE)") is None                      # revenue by country: not used
    assert canonical_column("Average bid size") is None


def test_header_row_is_found_in_both_layouts():
    assert find_header_row(_sheet_2013_layout([])) == 2                   # line 3 (2012-2016)
    later = pd.DataFrame([[None] * 3] * 5 + [[None, "Date", "Time"]])    # line 6, after an empty first column
    assert find_header_row(later) == 5


def test_clean_keeps_only_successful_eua_auctions_in_the_window():
    rows = [
        _row("2013-01-07", "T3PA", 6.0, 3_000_000, 9_000_000),                 # kept: cover 3
        _row("2013-01-08", "T3PA", 6.2, 2_000_000, 3_000_000, name="PL"),      # kept: cover 1.5
        _row("2013-01-08", "T2PA", 5.0, 1_000_000, 2_000_000),                 # phase 2 EUA: dropped
        _row("2013-01-09", "EAA3", 5.5, 500_000, 1_500_000),                   # aviation: dropped
        _row("2012-12-18", "T3PA", 6.5, 3_000_000, 6_000_000),                 # before 2013: dropped
        _row("2013-01-07", "T3PA", 6.0, 3_000_000, 9_000_000),                 # exact duplicate: dropped
        _row("2013-01-10", "T3PA", np.nan, 3_000_000, 2_000_000),              # no price: dropped
    ]
    df = tidy_sheet(_sheet_2013_layout(rows))
    df["source"] = "hand-built"
    kept, report = clean(df, start="2013-01-01", end="2013-12-31")

    assert report["rows_read"] == 7
    assert report["dropped_by_contract"] == {"T2PA": 1, "EAA3": 1}
    assert report["dropped_missing_or_zero_values"] == 1
    assert report["dropped_outside_window"] == {"2012": 1}
    assert report["dropped_duplicates"] == 1
    assert report["rows_kept"] == 2
    assert kept["zone"].tolist() == ["EU", "PL"]
    assert kept["cover"].tolist() == pytest.approx([3.0, 1.5])
    assert kept["datetime"].iloc[0] == pd.Timestamp("2013-01-07 11:00:00")


def test_clean_drops_cancelled_auctions():
    # from 2020 the files have a Status column; a cancelled auction has no price
    rows = [_row("2020-03-16", "T3PA", 20.0, 2_000_000, 4_000_000), _row("2020-03-17", "T3PA", np.nan, 2_000_000, 1_900_000)]
    df = tidy_sheet(_sheet_2013_layout(rows))
    df["status"] = ["successful", "cancelled"]
    df["source"] = "hand-built"
    kept, report = clean(df, start="2020-01-01", end="2020-12-31")
    assert report["dropped_cancelled"] == 1 and report["cancelled_dates"] == ["2020-03-17"]
    assert len(kept) == 1


def test_rows_after_the_window_are_not_counted_anywhere():
    # the current year's file grows after every auction: the report must not depend on the day of the download
    rows = [_row("2020-03-16", "T3PA", 20.0, 2_000_000, 4_000_000), _row("2020-03-17", "T3PA", np.nan, 2_000_000, 1_900_000)]
    later = [_row("2021-01-05", "T3PA", 30.0, 2_000_000, 4_000_000), _row("2021-01-06", "T3PA", np.nan, 2_000_000, 1_900_000)]
    status = ["successful", "cancelled"]

    def run(r, st):
        df = tidy_sheet(_sheet_2013_layout(r))
        df["status"] = st
        df["source"] = "hand-built"
        return clean(df, start="2020-01-01", end="2020-12-31")

    kept, report = run(rows, status)
    kept_later, report_later = run(rows + later, status + status)
    assert report_later == report
    assert report["rows_read"] == 2 and report["dropped_cancelled"] == 1 and report["dropped_outside_window"] == {}
    pd.testing.assert_frame_equal(kept_later, kept)

