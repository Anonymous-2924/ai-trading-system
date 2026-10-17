"""Indicator correctness, including hand calculations for Wilder smoothing."""

import math

import numpy as np
import pandas as pd
import pytest

from trading_system import indicators as ind


class TestWilderSmoothing:
    def test_seeded_with_sma_not_first_value(self):
        """Wilder's smoothing seeds with the SMA of the first `period` values.

        Hand calculation, period=2 over [1, 2, 3, 4]:
            seed  = (1+2)/2             = 1.5
            s[2]  = 1.5 + (3-1.5)/2     = 2.25
            s[3]  = 2.25 + (4-2.25)/2   = 3.125
        """
        out = ind.wilder_smooth(pd.Series([1.0, 2.0, 3.0, 4.0]), 2)
        assert math.isnan(out.iloc[0])
        assert out.iloc[1] == pytest.approx(1.5)
        assert out.iloc[2] == pytest.approx(2.25)
        assert out.iloc[3] == pytest.approx(3.125)

    def test_differs_from_an_ewm_seed(self):
        """An ewm(alpha=1/n, adjust=False) seed gives different numbers.

        This is the bug the brief calls out, so it is pinned by a test.
        """
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        wilder = ind.wilder_smooth(s, 3)
        ewm = s.ewm(alpha=1 / 3, adjust=False).mean()
        assert wilder.iloc[-1] != pytest.approx(ewm.iloc[-1])

    def test_nan_inside_the_seed_window_delays_the_start(self):
        s = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0])
        out = ind.wilder_smooth(s, 2)
        # The first clean 2-run ends at index 3.
        assert math.isnan(out.iloc[2])
        assert out.iloc[3] == pytest.approx(3.5)


class TestRSI:
    def test_hand_calculation_period_3(self):
        """closes 10,11,12,11,13,12,14 with period 3.

            gains  = 1, 1, 0, 2, 0, 2
            losses = 0, 0, 1, 0, 1, 0
            seedG  = (1+1+0)/3 = 0.666667      seedL = (0+0+1)/3 = 0.333333
            then Wilder:
              avgG = 1.111111, 0.740741, 1.160494
              avgL = 0.222222, 0.481481, 0.320988
            RS   = 1.160494 / 0.320988 = 3.615385
            RSI  = 100 - 100/(1+RS)   = 78.333333
        """
        close = pd.Series([10, 11, 12, 11, 13, 12, 14], dtype="float64")
        assert ind.rsi(close, 3).iloc[-1] == pytest.approx(78.333333, abs=1e-5)

    def test_bounds_and_edges(self):
        rising = pd.Series(np.arange(1, 60, dtype="float64"))
        assert ind.rsi(rising, 14).iloc[-1] == pytest.approx(100.0)
        flat = pd.Series([50.0] * 40)
        assert ind.rsi(flat, 14).iloc[-1] == pytest.approx(50.0)
        falling = pd.Series(np.arange(60, 1, -1, dtype="float64"))
        assert ind.rsi(falling, 14).iloc[-1] == pytest.approx(0.0, abs=1e-9)

    def test_stays_within_0_100(self, frame_factory):
        df = frame_factory(400, seed=5)
        r = ind.rsi(df["close"], 14).dropna()
        assert r.min() >= 0.0 and r.max() <= 100.0


class TestATRAndTrueRange:
    def test_true_range_hand_calculation(self):
        h = pd.Series([11, 12, 13, 12.5, 14.0])
        l = pd.Series([9, 10, 11, 10.5, 11.0])
        c = pd.Series([10, 11, 12, 11, 13.0])
        assert list(ind.true_range(h, l, c)) == [2.0, 2.0, 2.0, 2.0, 3.0]

    def test_atr_hand_calculation_period_3(self):
        """TR = 2,2,2,2,3 with period 3.

            seed = (2+2+2)/3 = 2
            s[3] = 2 + (2-2)/3       = 2
            s[4] = 2 + (3-2)/3       = 2.333333
        """
        h = pd.Series([11, 12, 13, 12.5, 14.0])
        l = pd.Series([9, 10, 11, 10.5, 11.0])
        c = pd.Series([10, 11, 12, 11, 13.0])
        atr = ind.atr(h, l, c, 3)
        assert atr.iloc[2] == pytest.approx(2.0)
        assert atr.iloc[3] == pytest.approx(2.0)
        assert atr.iloc[4] == pytest.approx(2.333333, abs=1e-6)

    def test_natr_is_atr_over_price(self, frame_factory):
        df = frame_factory(200, seed=2)
        a = ind.atr(df["high"], df["low"], df["close"], 14).iloc[-1]
        n = ind.natr(df["high"], df["low"], df["close"], 14).iloc[-1]
        assert n == pytest.approx(100.0 * a / df["close"].iloc[-1])


class TestADX:
    def test_pure_uptrend_has_high_adx_and_positive_di_bias(self):
        n = 120
        close = pd.Series(np.linspace(100, 300, n))
        high, low = close * 1.01, close * 0.99
        out = ind.adx(high, low, close, 14)
        assert out["adx"].iloc[-1] > 40
        assert out["plus_di"].iloc[-1] > out["minus_di"].iloc[-1]

    def test_pure_downtrend_flips_the_di_bias(self):
        n = 120
        close = pd.Series(np.linspace(300, 100, n))
        high, low = close * 1.01, close * 0.99
        out = ind.adx(high, low, close, 14)
        assert out["adx"].iloc[-1] > 40
        assert out["minus_di"].iloc[-1] > out["plus_di"].iloc[-1]

    def test_adx_is_unsigned_and_bounded(self, frame_factory):
        df = frame_factory(400, seed=9)
        a = ind.adx(df["high"], df["low"], df["close"], 14)["adx"].dropna()
        assert a.min() >= 0 and a.max() <= 100


class TestMACD:
    def test_line_is_fast_minus_slow_ema(self, frame_factory):
        c = frame_factory(300, seed=3)["close"]
        m = ind.macd(c, 12, 26, 9)
        expected = ind.ema(c, 12).iloc[-1] - ind.ema(c, 26).iloc[-1]
        assert m["macd"].iloc[-1] == pytest.approx(expected)

    def test_hist_is_line_minus_signal(self, frame_factory):
        c = frame_factory(300, seed=4)["close"]
        m = ind.macd(c)
        assert m["hist"].iloc[-1] == pytest.approx(
            m["macd"].iloc[-1] - m["signal"].iloc[-1]
        )

    def test_line_is_negative_through_a_sustained_decline(self, frame_factory):
        c = frame_factory(300, seed=3, end_multiplier=0.28)["close"]
        assert ind.macd(c)["macd"].iloc[-1] < 0


class TestRemainingIndicators:
    def test_ema_is_sma_seeded(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        e = ind.ema(s, 3)
        assert math.isnan(e.iloc[1])
        assert e.iloc[2] == pytest.approx(2.0)          # SMA(1,2,3)
        assert e.iloc[3] == pytest.approx(2.0 + 0.5 * (4 - 2))  # alpha = 2/4

    def test_obv_accumulates_signed_volume(self):
        c = pd.Series([10.0, 11.0, 10.5, 12.0])
        v = pd.Series([100.0, 200.0, 300.0, 400.0])
        assert list(ind.obv(c, v)) == [0.0, 200.0, -100.0, 300.0]

    def test_mfi_and_cmf_are_bounded(self, frame_factory):
        df = frame_factory(300, seed=6)
        m = ind.mfi(df["high"], df["low"], df["close"], df["volume"], 14).dropna()
        cm = ind.cmf(df["high"], df["low"], df["close"], df["volume"], 20).dropna()
        assert m.min() >= 0 and m.max() <= 100
        assert cm.min() >= -1 and cm.max() <= 1

    def test_bollinger_pct_b_and_width(self, frame_factory):
        df = frame_factory(200, seed=7)
        bb = ind.bollinger(df["close"], 20, 2.0)
        last = bb.iloc[-1]
        assert last["lower"] < last["mid"] < last["upper"]
        expected = (df["close"].iloc[-1] - last["lower"]) / (last["upper"] - last["lower"])
        assert last["pct_b"] == pytest.approx(expected)
        assert last["width"] > 0

    def test_donchian_position_is_0_to_1_inside_the_channel(self, frame_factory):
        df = frame_factory(200, seed=8)
        d = ind.donchian(df["high"], df["low"], df["close"], 20).dropna()
        assert d["position"].between(-0.5, 1.5).all()

    def test_zscore_of_a_constant_series_is_nan_not_inf(self):
        z = ind.zscore(pd.Series([5.0] * 40), 20)
        assert math.isnan(z.iloc[-1])

    def test_trailing_return_and_skew(self):
        c = pd.Series(np.linspace(100, 200, 120))
        assert ind.trailing_return(c, 60).iloc[-1] > 0
        assert not math.isnan(ind.rolling_skew(c, 60).iloc[-1])


def test_no_pandas_ta_dependency():
    """pandas_ta imports numpy.NaN, removed in numpy 2.x.  We must not use it."""
    import pathlib
    import re

    # Match an actual import, not the prose in the docstrings explaining why
    # we do not use it.
    pattern = re.compile(r"^\s*(?:import\s+pandas_ta|from\s+pandas_ta\b)", re.M)
    root = pathlib.Path(__file__).resolve().parents[1]
    for folder in ("src", "scripts", "dashboard"):
        for path in (root / folder).rglob("*.py"):
            assert not pattern.search(path.read_text(encoding="utf-8")), path
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    assert not re.search(r"^\s*pandas[-_]ta", requirements, re.M)


def test_numpy_2_compatible():
    assert int(np.__version__.split(".")[0]) >= 2
    assert not hasattr(np, "NaN")
