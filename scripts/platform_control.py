"""Post hoc check on question 3 (added on 28 November 2026, after the results): the chosen test with a control for
the platform of auction t. Not part of the design; see `eua_auctions.platform_control`.

Writes results/platform_control.json.
"""
import json
from pathlib import Path

from eua_auctions.cover_signal import HORIZONS, QUANTILES, TEST, TRAIN, lags_for, sample, select_on_train
from eua_auctions.data import load
from eua_auctions.platform_control import leave_one_year_out, platform_test

RESULTS = Path("results")
ADDED = "2026-11-28"


def _round(x):
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    if isinstance(x, float):
        return round(x, 4)
    return x


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    df, _ = load()
    _, chosen = select_on_train(df)
    k, q = chosen["k"], chosen["q"]
    after_2013 = df[df["date"] >= TRAIN[0]]
    assert not after_2013["date"].duplicated().any()  # one auction per day from 2014: dates identify auctions
    zone = after_2013.set_index("date")["zone"]

    def with_zone(period, kk=k, qq=q):
        s = sample(df, *period, kk, qq)
        s["zone"] = s["date"].map(zone)
        assert s["zone"].notna().all()
        return s

    test, train = with_zone(TEST), with_zone(TRAIN)
    variants = []
    for kk in HORIZONS:
        for qq in QUANTILES:
            r = platform_test(with_zone(TEST, kk, qq), lags_for(kk))
            variants.append({"k": kk, "q": qq, **{key: r[key] for key in ("n", "high_minus_low", "t_hac", "p_hac")}})
    results = {
        "note": ("Post hoc, not part of the design: chosen on 28 November 2026 after all results had been seen. "
                 "The chosen variant with one dummy per platform of auction t (base: the common platform), same "
                 "target and same HAC errors. cover_signal.py and results/cover_signal.json are unchanged."),
        "added": ADDED, "chosen": {"k": k, "q": q}, "hac_lags": lags_for(k), "base_platform": "EU",
        "test_2021_2026": platform_test(test, lags_for(k)),
        "train_2014_2020": platform_test(train, lags_for(k)),
        "test_leave_one_year_out": leave_one_year_out(test, lags_for(k)),
        "test_9_variants_with_control": variants,
        "test_platform_share_by_bucket_pct": {
            b: {z: 100 * float((test.loc[test["bucket"] == b, "zone"] == z).mean())
                for z in sorted(test["zone"].unique())}
            for b in ("low", "mid", "high")},
    }
    (RESULTS / "platform_control.json").write_text(json.dumps(_round(results), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
