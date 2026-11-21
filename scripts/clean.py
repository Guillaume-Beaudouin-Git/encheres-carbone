"""Read the 15 EEX files, clean them, and write the cleaning report to results/cleaning.json."""
import json
from pathlib import Path

from eua_auctions.data import load

RESULTS = Path("results")


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    df, report = load()
    (RESULTS / "cleaning.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"{len(df)} EUA auctions from {df['date'].min().date()} to {df['date'].max().date()}")


if __name__ == "__main__":
    main()
