"""Relative strength, beta, opening range and relative volume.

These came out of the intraday playbook we were given. The playbook assumes
minute-by-minute monitoring, which a system that runs twice a day cannot do,
so what is tested here is the honest translation of it onto daily and
15-minute bars.
"""

import math

import numpy as np
import pandas as pd
import pytest

from trading_system import indicators as ind
from trading_system.features import extract_features
from trading_system.scoring import score_featureset, unweighted_features


def daily(series, index):
    return pd.DataFrame(
        {
            "open": series.shift(1).bfill(),
            "high": series * 1.01,
            "low": series * 0.99,
            "close": series,
            "volume": np.full(len(series), 2_000_000.0),
        },
        index=index,
    )


@pytest.fixture
def index():
    return pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")


class TestRelativeStrength:
    def test_outperformance_is_positive(self, index):
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.004)), index=index)
        bench = pd.Series(100 * np.cumprod(np.full(300, 1.001)), index=index)
        assert ind.relative_strength(stock, bench, 20).iloc[-1] > 0

    def test_underperformance_is_negative(self, index):
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.001)), index=index)
        bench = pd.Series(100 * np.cumprod(np.full(300, 1.004)), index=index)
        assert ind.relative_strength(stock, bench, 20).iloc[-1] < 0

    def test_a_stock_against_itself_is_exactly_zero(self, index):
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=index)
        assert ind.relative_strength(stock, stock, 20).iloc[-1] == pytest.approx(0.0)

    def test_misaligned_dates_are_intersected_not_guessed(self, index):
        stock = pd.Series(np.linspace(100, 200, 300), index=index)
        short = pd.Series(np.linspace(100, 150, 120), index=index[:120])
        result = ind.relative_strength(stock, short, 20)
        assert len(result) == 120

    def test_a_rising_stock_in_a_faster_market_still_scores_negative(self, index):
        """The whole point: up 5% is not good if the market is up 13%."""
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.0025)), index=index)
        hot = pd.Series(100 * np.cumprod(np.full(300, 1.0060)), index=index)
        fs = extract_features(
            "X", daily(stock, index), benchmarks={"SPY": daily(hot, index), "QQQ": daily(hot, index)}
        )
        assert fs.values["rs_spy20"] < 0
        assert score_featureset(fs).feature_scores["rs_spy20"] < 0

    def test_the_same_stock_scores_higher_against_a_flat_market(self, index):
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.0025)), index=index)
        flat = pd.Series(100 * np.cumprod(np.full(300, 1.0000)), index=index)
        hot = pd.Series(100 * np.cumprod(np.full(300, 1.0060)), index=index)
        leader = score_featureset(
            extract_features("X", daily(stock, index),
                            benchmarks={"SPY": daily(flat, index), "QQQ": daily(flat, index)})
        )
        laggard = score_featureset(
            extract_features("X", daily(stock, index),
                            benchmarks={"SPY": daily(hot, index), "QQQ": daily(hot, index)})
        )
        assert leader.composite > laggard.composite


class TestBeta:
    def test_a_series_against_itself_is_one(self, index):
        rng = np.random.default_rng(4)
        spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.009, 300)), index=index)
        assert ind.rolling_beta(spy, spy, 60).iloc[-1] == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.parametrize("target", [0.5, 1.8])
    def test_a_constructed_beta_is_recovered(self, index, target):
        rng = np.random.default_rng(7)
        spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.009, 300)), index=index)
        moves = spy.pct_change().fillna(0.0).to_numpy() * target
        stock = pd.Series(100 * np.cumprod(1 + moves + rng.normal(0, 0.003, 300)), index=index)
        assert ind.rolling_beta(stock, spy, 60).iloc[-1] == pytest.approx(target, abs=0.15)

    def test_a_flat_benchmark_gives_no_beta_rather_than_a_huge_one(self, index):
        """A benchmark with no variance once produced a beta of 6.5e10, which
        would then have driven position sizing to nonsense."""
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.0025)), index=index)
        flat = pd.Series(100 * np.cumprod(np.full(300, 1.0005)), index=index)
        assert math.isnan(ind.rolling_beta(stock, flat, 60).iloc[-1])

    def test_absurd_betas_are_refused(self, index):
        series = ind.rolling_beta(
            pd.Series(np.linspace(1, 1000, 300), index=index),
            pd.Series(100 + np.sin(np.arange(300)) * 1e-6, index=index),
            60,
        ).dropna()
        assert (series.abs() <= 5.0).all()


def intraday_session(day, base=100.0, bars=26, volume=10_000.0, breakout=False):
    times = pd.date_range(f"{day} 13:30", periods=bars, freq="15min", tz="UTC")
    closes = np.full(bars, base) + np.linspace(0, 0.6, bars)
    if breakout:
        closes[2:] = closes[1] + np.linspace(0.5, 5.0, bars - 2)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.3, "low": closes - 0.3,
         "close": closes, "volume": np.full(bars, volume)},
        index=times,
    )


class TestOpeningRange:
    def test_a_breakout_scores_above_one(self):
        frame = pd.concat([intraday_session("2026-10-22"),
                           intraday_session("2026-10-23", breakout=True)])
        assert ind.opening_range(frame, bars=1)["position"] > 1.0

    def test_the_range_comes_from_the_first_bar_only(self):
        frame = intraday_session("2026-10-23", breakout=True)
        orb = ind.opening_range(frame, bars=1)
        first = frame.iloc[0]
        assert orb["high"] == pytest.approx(float(first["high"]))
        assert orb["low"] == pytest.approx(float(first["low"]))

    def test_an_empty_frame_gives_no_range(self):
        assert ind.opening_range(pd.DataFrame()) == {}
        assert ind.opening_range(None) == {}

    def test_missing_intraday_leaves_the_feature_neutral(self, index):
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=index)
        fs = extract_features("X", daily(stock, index), intraday=None)
        assert math.isnan(fs.values["orb_pos"])
        assert score_featureset(fs).feature_scores["orb_pos"] == 0.0


class TestRelativeVolume:
    def test_triple_volume_reads_three(self):
        frame = pd.concat([
            intraday_session("2026-10-21"),
            intraday_session("2026-10-22"),
            intraday_session("2026-10-23", volume=30_000.0),
        ])
        assert ind.relative_volume(frame) == pytest.approx(3.0, abs=0.01)

    def test_it_compares_like_for_like_within_the_session(self):
        """A reading taken two bars in must not be measured against whole
        prior days, or every morning would look like a volume collapse."""
        full = pd.concat([intraday_session("2026-10-21"), intraday_session("2026-10-22")])
        partial = pd.concat([intraday_session("2026-10-21"),
                             intraday_session("2026-10-22").iloc[:2]])
        assert ind.relative_volume(partial) == pytest.approx(
            ind.relative_volume(full), abs=0.05
        )

    def test_one_session_is_not_enough_history(self):
        assert math.isnan(ind.relative_volume(intraday_session("2026-10-23")))

    def test_the_score_is_capped_because_the_feed_is_partial(self, index):
        """IEX sees a slice of real volume, so rvol confirms, never decides."""
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=index)
        huge = pd.concat([intraday_session("2026-10-22"),
                          intraday_session("2026-10-23", volume=500_000.0)])
        fs = extract_features("X", daily(stock, index), intraday=huge)
        assert abs(score_featureset(fs).feature_scores["rvol"]) <= 0.6


class TestFeatureInventory:
    def test_the_scored_count_stays_near_thirty(self):
        from trading_system.features import feature_count

        assert 20 <= feature_count() <= 30

    def test_no_scored_feature_is_left_without_a_weight(self):
        """A feature added without a weight is computed and then ignored —
        silently, which is the worst kind of bug."""
        assert unweighted_features() == []

    def test_atr_is_a_diagnostic_not_a_scored_feature(self, index):
        """ATR has no direction, so it is carried for stop sizing only.
        Reading it from the wrong place yields NaN and the risk module then
        falls back to a flat band — a stop that looks real and is not."""
        stock = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=index)
        fs = extract_features("X", daily(stock, index))
        assert "atr14" not in fs.values
        assert math.isfinite(fs.diagnostics["atr14"])

    def test_the_rule_engine_reads_atr_from_diagnostics(self, index):
        from trading_system.rule_engine import run_rule_engine

        stock = pd.Series(100 * np.cumprod(np.full(300, 1.002)), index=index)
        result = run_rule_engine(["X"], {"X": daily(stock, index)})
        assert math.isfinite(result.atr_map()["X"]), "stops would silently use a flat band"
