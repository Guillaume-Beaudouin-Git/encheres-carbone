"""Download, read and clean the EEX primary market auction reports for EU emission allowances.

Source: EEX, "EUA Emission Spot Primary Market Auction Report", one spreadsheet per year. The files are public
but they are EEX's data: they are downloaded into `data/` (not versioned) and never redistributed here.

The layout changes over the years, so every file is read the same way:
- the sheet is "Primary Market Auction" (2012-2025) or "EU ETS1" (2026); any other sheet, such as a future
  "EU ETS2" sheet, is ignored;
- the header row is found by looking for the cell "Date" (line 3 of the sheet in 2012-2016, line 6 from 2017);
- column names are mapped to one set of short names (`canonical_column`); columns not used here, such as the
  revenue by member state, are dropped.

`clean` then keeps one row per successful auction of general EU allowances (EUA). Each rule and the number of
rows it removes is returned in a report, so the README can state it.
"""
from __future__ import annotations

import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL_ARCHIVE = (
    "https://www.eex.com/fileadmin/EEX/Downloads/Markets/Environmentals/EUA_Emission_Spot_Primary_Market_Auction_Report/"
    "Archive_Reports/emission-spot-primary-market-auction-report-2012-2025-data.zip"
)
URL_2026 = "https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-2026-data.xlsx"

RAW = Path("data/raw")
ARCHIVE_DIR = "emission-spot-primary-market-auction-report-2012-2025-data"
FILE_2026 = "emission-spot-primary-market-auction-report-2026-data.xlsx"

# EEX keeps the contract code T3PA for general allowances in phase 4 (2021-2030): the auction names say
# "Auction 4. Period" but the code does not change. T2PA = phase 2 EUA; EAA2 / EAA3 = aviation allowances (EUAA).
EUA_CONTRACT = "T3PA"
SHEETS = ("Primary Market Auction", "EU ETS1")

# Analysis window: phase 3 starts on 1 January 2013. The 2026 file grows after every auction, so the window is
# fixed at the last auction in the file used for this page; a later download gives the same numbers.
START, END = "2013-01-01", "2026-11-20"


# ---------------------------------------------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------------------------------------------

def _download(url: str, path: Path, attempts: int = 3, pause_s: float = 5.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for _ in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
            with urllib.request.urlopen(request, timeout=120) as response:
                path.write_bytes(response.read())
            return
        except Exception as error:  # network or server momentarily unavailable
            last = error
            time.sleep(pause_s)
    raise RuntimeError(f"download failed: {url}") from last


def _safe_extract(archive: Path, target: Path) -> None:
    """Extract a zip archive, refusing members that would land outside `target`."""
    target = target.resolve()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            destination = (target / member.filename).resolve()
            if target not in destination.parents and destination != target:
                raise ValueError(f"unsafe path in archive: {member.filename}")
        z.extractall(target)


def download_all(raw: Path = RAW) -> None:
    """Download the 2012-2025 archive and the 2026 file into `raw`, and unzip the archive."""
    archive = raw / f"{ARCHIVE_DIR}.zip"
    _download(URL_ARCHIVE, archive)
    if (raw / ARCHIVE_DIR).exists():
        shutil.rmtree(raw / ARCHIVE_DIR)
    _safe_extract(archive, raw)
    _download(URL_2026, raw / FILE_2026)


def raw_files(raw: Path = RAW) -> list[Path]:
    files = sorted((raw / ARCHIVE_DIR).glob("*.xls*")) + [raw / FILE_2026]
    missing = [f for f in files if not f.exists()]
    if missing or len(files) < 2:
        raise FileNotFoundError("raw files missing: run `uv run python scripts/download.py` first")
    return files


# ---------------------------------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------------------------------

def canonical_column(name: object) -> str | None:
    """Short name for an EEX column, whatever the year's spelling; None for a column not used here."""
    n = re.sub(r"\s+", " ", str(name)).strip().lower().replace("eur/", "€/").replace("eur", "€")
    exact = {
        "date": "date", "time": "time", "auction time": "time", "auction name": "auction_name",
        "contract": "contract", "certificate": "certificate", "status": "status",
        "total amount of bids": "bid_volume", "cover ratio": "cover_ratio", "total number of bidders": "n_bidders",
        "country": "zone", "zone": "zone",
    }
    if n in exact:
        return exact[n]
    prefixes = [
        ("auction price", "price"), ("minimum bid", "min_bid"), ("minimal price", "min_bid"),
        ("maximum bid", "max_bid"), ("maximal price", "max_bid"), ("mean", "mean_bid"), ("median", "median_bid"),
        ("auction volume", "volume"), ("total revenue", "revenue"),
    ]
    for prefix, short in prefixes:
        if n.startswith(prefix):
            return short
    if n.startswith("number of succes") and n.endswith("bidders"):  # "Succesful" is misspelt in 2016
        return "n_successful_bidders"
    return None


def find_header_row(sheet: pd.DataFrame, max_rows: int = 15) -> int:
    """Index of the first row that has a cell equal to "Date"."""
    for i in range(min(max_rows, len(sheet))):
        if any(str(v).strip() == "Date" for v in sheet.iloc[i].tolist()):
            return i
    raise ValueError("no header row with a 'Date' cell")


def tidy_sheet(sheet: pd.DataFrame) -> pd.DataFrame:
    """From a sheet read without header: locate the header, rename the columns, drop the unused ones."""
    h = find_header_row(sheet)
    names = [canonical_column(c) for c in sheet.iloc[h].tolist()]
    body = sheet.iloc[h + 1:].copy()
    body.columns = [n if n is not None else f"_unused_{j}" for j, n in enumerate(names)]
    body = body.loc[:, [c for c in body.columns if not c.startswith("_unused_")]]
    if body.columns.duplicated().any():
        raise ValueError(f"two columns map to the same name: {list(body.columns)}")
    return body.reset_index(drop=True)


def read_file(path: Path) -> pd.DataFrame:
    sheets = pd.ExcelFile(path).sheet_names
    sheet = next((s for s in SHEETS if s in sheets), None)
    if sheet is None:
        raise ValueError(f"{path.name}: none of the sheets {SHEETS} in {sheets}")
    df = tidy_sheet(pd.read_excel(path, sheet_name=sheet, header=None))
    df["source"] = path.name
    return df


def read_all(raw: Path = RAW) -> pd.DataFrame:
    return pd.concat([read_file(f) for f in raw_files(raw)], ignore_index=True)


# ---------------------------------------------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------------------------------------------

NUMERIC = ["price", "min_bid", "max_bid", "mean_bid", "median_bid", "volume", "bid_volume", "cover_ratio",
           "n_bidders", "n_successful_bidders", "revenue"]
REQUIRED = ["price", "volume", "bid_volume", "n_bidders", "mean_bid"]


def _zone(row: pd.Series) -> str:
    """Auctioning platform: EU (common platform), DE, PL or XI (Northern Ireland).

    The zone column is missing in 2016 only; there the auction name is "EU (TCAP)", "DE" or "PL"."""
    zone = row.get("zone")
    if isinstance(zone, str) and zone.strip():
        return zone.strip()
    name = str(row.get("auction_name", "")).strip()
    return "EU" if name.startswith("EU") else name


def _time_of_day(value: object) -> pd.Timedelta:
    """The time column is an Excel time (read as 1970-01-01 hh:mm:ss or as datetime.time) or a string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.Timedelta(0)
    t = pd.to_datetime(str(value) if not hasattr(value, "hour") else value.strftime("%H:%M:%S"), errors="coerce")
    if pd.isna(t):
        return pd.Timedelta(0)
    return pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)


def clean(df: pd.DataFrame, start: str = START, end: str = END) -> tuple[pd.DataFrame, dict]:
    """One row per successful EUA auction in [start, end], sorted by time, and a report of every rule applied."""
    report: dict = {"rows_read": int(len(df))}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()  # 2016 dates carry 09:00
    n = len(df)
    df = df[df["date"].notna()]
    report["dropped_no_date"] = int(n - len(df))

    contracts = df["contract"].astype(str).str.strip()
    report["dropped_by_contract"] = {str(k): int(v) for k, v in contracts[contracts != EUA_CONTRACT].value_counts().items()}
    report["dropped_contract_first_last_date"] = {
        str(c): [g["date"].min().strftime("%Y-%m-%d"), g["date"].max().strftime("%Y-%m-%d")]
        for c, g in df[contracts != EUA_CONTRACT].groupby(contracts[contracts != EUA_CONTRACT])}
    df = df[contracts == EUA_CONTRACT].copy()

    # aviation allowances must all carry an EAA code; check that none slipped through under T3PA
    aviation = df["auction_name"].astype(str).str.contains("EUAA")
    if "certificate" in df.columns:
        aviation |= df["certificate"].astype(str).str.strip().eq("EUAA")
    report["dropped_aviation_under_eua_code"] = int(aviation.sum())
    df = df[~aviation]

    status = df["status"].astype(str).str.strip().str.lower() if "status" in df.columns else pd.Series("", index=df.index)
    cancelled = status.eq("cancelled")
    report["dropped_cancelled"] = int(cancelled.sum())
    report["cancelled_dates"] = sorted(df.loc[cancelled, "date"].dt.strftime("%Y-%m-%d").tolist())
    df = df[~cancelled].copy()

    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    missing = df[REQUIRED].isna().any(axis=1) | (df["volume"] <= 0) | (df["price"] <= 0)
    report["dropped_missing_or_zero_values"] = int(missing.sum())
    df = df[~missing].copy()

    outside = (df["date"] < pd.Timestamp(start)) | (df["date"] > pd.Timestamp(end))
    report["dropped_outside_window"] = {str(k): int(v) for k, v in df.loc[outside, "date"].dt.year.value_counts().sort_index().items()}
    df = df[~outside].copy()

    df["zone"] = df.apply(_zone, axis=1)
    # 14 days of 2013 have two auctions (EU at 11:00, PL at 15:00): the time of day orders them
    df["datetime"] = df["date"] + df["time"].map(_time_of_day)
    n = len(df)
    df = df.drop_duplicates(subset=["datetime", "zone", "price", "volume"])
    report["dropped_duplicates"] = int(n - len(df))

    df = df.sort_values("datetime").reset_index(drop=True)
    df["year"] = df["date"].dt.year
    # cover ratio = total bid volume / volume offered; EEX rounds it to two decimals
    df["cover"] = df["bid_volume"] / df["volume"]
    gap = (df["cover"] - df["cover_ratio"]).abs()
    report["cover_ratio_check"] = {"max_abs_gap_vs_eex": round(float(gap.max()), 4),
                                   "rows_gap_above_0.01": int((gap > 0.01).sum())}
    report["rows_kept"] = int(len(df))
    report["rows_kept_by_year"] = {int(k): int(v) for k, v in df["year"].value_counts().sort_index().items()}
    report["rows_kept_by_zone"] = {str(k): int(v) for k, v in df["zone"].value_counts().items()}
    report["years_by_zone"] = {str(z): [int(g["year"].min()), int(g["year"].max())] for z, g in df.groupby("zone")}
    report["window"] = [start, end]
    report["same_day_auctions"] = int(df["date"].duplicated().sum())
    cols = ["datetime", "date", "year", "zone", "price", "min_bid", "max_bid", "mean_bid", "median_bid", "volume",
            "bid_volume", "cover", "cover_ratio", "n_bidders", "n_successful_bidders", "revenue", "source"]
    return df[cols], report


def load(raw: Path = RAW, start: str = START, end: str = END) -> tuple[pd.DataFrame, dict]:
    return clean(read_all(raw), start, end)
