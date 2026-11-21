"""Question 3: does a low or high cover ratio announce the clearing price change over the next k auctions?

Parameters are chosen on 2014-2020 and judged once on 2021-2026 (see `eua_auctions.cover_signal`).
Writes results/cover_signal.json and figures/Q3_cover_signal_test.png.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from eua_auctions import style
from eua_auctions.cover_signal import (HORIZONS, QUANTILES, TEST, TRAIN, WINDOW, bucket_test, forecast_comparison,
                                       grid, lags_for, sample, select_on_train)
from eua_auctions.data import load

FIGURES, RESULTS = Path("figures"), Path("results")


def _round(x):
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    if isinstance(x, float):
        return round(x, 4)
    return x


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    style.apply()
    df, _ = load()

    # 1. Training years only: the 9 variants, and the choice
    train_grid, chosen = select_on_train(df)
    k, q = chosen["k"], chosen["q"]

    # 2. The test: the chosen variant, once, on 2021-2026
    test = bucket_test(sample(df, *TEST, k, q), lags_for(k))
    train = bucket_test(sample(df, *TRAIN, k, q), lags_for(k))
    forecast = forecast_comparison(df, k, q)

    # 3. The one robustness check: forward change from the next auction (t+1 to t+1+k)
    robust_test = bucket_test(sample(df, *TEST, k, q, skip=1), lags_for(k))
    robust_train = bucket_test(sample(df, *TRAIN, k, q, skip=1), lags_for(k))

    # 4. Transparency: the 9 variants on the test years (not used for any choice)
    test_grid = grid(df, *TEST)

    tr_sample = sample(df, *TRAIN, k, q)
    results = {
        "design": {
            "window_auctions": WINDOW, "horizons_k": list(HORIZONS), "quantiles_q": list(QUANTILES),
            "train": list(TRAIN), "test": list(TEST), "hac_lags": "2k (Newey-West)",
            "selection": "largest |HAC t| of mean(high) - mean(low) on the training years",
            "variants_tried": len(HORIZONS) * len(QUANTILES) + 1,
        },
        "chosen": chosen,
        "train_last_target_date": str(tr_sample["target_date"].max())[:10],
        "train_chosen": train,
        "test_chosen": test,
        "forecast_test": forecast,
        "robustness_skip_one": {"train": robust_train, "test": robust_test},
        "train_grid": train_grid.to_dict(orient="records"),
        "test_grid_for_transparency": test_grid.to_dict(orient="records"),
    }
    (RESULTS / "cover_signal.json").write_text(json.dumps(_round(results), indent=2))

    # Figure: high - low difference with its 95% HAC interval, the 9 variants, training and test
    labels = [f"k={r.k}\nq={r.q:g}" for r in train_grid.itertuples()]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for table, offset, colour, name in [(train_grid, -0.14, style.BLUE, "2014-2020 (choice)"),
                                        (test_grid, 0.14, style.ORANGE, "2021-2026 (test)")]:
        ax.errorbar(x + offset, table["high_minus_low"], yerr=1.96 * table["se_hac"], fmt="o", ms=6, color=colour,
                    elinewidth=1.6, capsize=0, label=name)
    i = int(train_grid.index[(train_grid["k"] == k) & (train_grid["q"] == q)][0])
    ax.axvspan(i - 0.42, i + 0.42, color=style.GREY, alpha=0.12, linewidth=0)
    ax.text(i, ax.get_ylim()[1], "chosen on\n2014-2020", ha="center", va="top", fontsize=8.5, color=style.INK_2)
    ax.axhline(0, color=style.INK_2, lw=0.9)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean change after high cover\nminus after low cover (% of price)")
    ax.set_title("Does the cover ratio announce the next price moves? High minus low, 95% HAC intervals")
    ax.legend(loc="lower left", ncols=2)
    ax.text(0, -0.24, "k = horizon in auctions; q = share of auctions called low (and high) cover, by rank among the "
            f"previous {WINDOW} auctions. Source: EEX auction reports.", transform=ax.transAxes, fontsize=8,
            color=style.INK_2)
    fig.savefig(FIGURES / "Q3_cover_signal_test.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    print("Training grid (2014-2020):")
    print(train_grid.round(3).to_string())
    print("Chosen:", chosen)
    print("Train:", json.dumps(_round(train), indent=1))
    print("Test:", json.dumps(_round(test), indent=1))
    print("Forecast:", json.dumps(_round(forecast), indent=1))
    print("Robustness (skip one):", json.dumps(_round({"train": robust_train, "test": robust_test}), indent=1))
    print("Test grid (transparency):")
    print(test_grid.round(3).to_string())


if __name__ == "__main__":
    main()
