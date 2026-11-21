"""Download the EEX auction reports into data/raw/ (a few seconds): the 2012-2025 archive and the 2026 file.

The 2026 file grows after every auction; the analysis stops at the date set in `eua_auctions.data.END`.
"""
from eua_auctions.data import RAW, download_all

if __name__ == "__main__":
    download_all(RAW)
    print(f"EEX files downloaded into {RAW}/")
