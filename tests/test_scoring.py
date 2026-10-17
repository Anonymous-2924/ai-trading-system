"""Feature extraction and the weighted ensemble, including the MACD 60/40 rule."""

import numpy as np
import pytest

from trading_system.features import DIMENSIONS, MIN_BARS, extract_features, feature_count
from trading_system.scoring import (
    DEFAULT_DIMENSION_WEIGHTS,
    MACD_MOMENTUM_SHARE,
    MACD_TREND_SHARE,
    feature_weights,
    macd_effective_weights,
    score_featureset,
)


class TestFeatures:
    def test_feature_count_is_in_the_20_to_30_band(self):
        n = feature_count()
        assert 20 <= n <= 30, f"the brief asks for 20-30 features, got {n}"

    def test_every_dimension_is_populated(self, frame_factory):
        fs = extract_features("TEST", frame_factory(300, seed=1))
        for dim in DIMENSIONS:
            assert fs.by_dimension(dim), f"dimension {dim} has no features"

    def test_all_five_dimensions_present(self, frame_factory):
        fs = extract_features("TEST", frame_factory(300, seed=1))
        assert set(fs.dimension_of.values()) == set(DIMENSIONS)

    def test_short_history_warns_rather_than_raising(self, frame_factory):
        fs = extract_features("TEST", frame_factory(40, seed=1))
        assert fs.warnings
        assert fs.bars_available == 40

    def test_missing_column_raises(self, frame_factory):
        df = frame_factory(100, seed=1).drop(columns=["volume"])
        with pytest.raises(ValueError, match="missing columns"):
            extract_features("TEST", df)

    def test_features_are_json_safe_floats(self, frame_factory):
        fs = extract_features("TEST", frame_factory(300, seed=1))
        assert all(isinstance(v, float) for v in fs.values.values())


class TestMACDWeighting:
    def test_effective_split_is_exactly_60_40(self):
        slots = macd_effective_weights()
        trend_contribution = DEFAULT_DIMENSION_WEIGHTS["trend"] * slots["macd_line"]
        mom_contribution = DEFAULT_DIMENSION_WEIGHTS["momentum"] * slots["macd_hist_pct"]
        total = trend_contribution + mom_contribution
        assert trend_contribution / total == pytest.approx(MACD_TREND_SHARE)
        assert mom_contribution / total == pytest.approx(MACD_MOMENTUM_SHARE)
        assert trend_contribution / mom_contribution == pytest.approx(1.5)

    def test_split_survives_reweighting_the_dimensions(self):
        custom = dict(DEFAULT_DIMENSION_WEIGHTS, trend=0.40, momentum=0.10)
        slots = macd_effective_weights(custom)
        ratio = (custom["trend"] * slots["macd_line"]) / (
            custom["momentum"] * slots["macd_hist_pct"]
        )
        assert ratio == pytest.approx(MACD_TREND_SHARE / MACD_MOMENTUM_SHARE)

    def test_each_dimension_weights_sum_to_one(self):
        for dim, weights in feature_weights().items():
            assert sum(weights.values()) == pytest.approx(1.0), dim


class TestSustainedDeclineRegression:
    """The failure the brief calls out by name.

    During a long decline the MACD histogram turns positive on every bounce.
    Scoring the histogram alone makes a ~72% drawdown read BULLISH.  Because
    the LINE (position versus zero) carries 60% of the MACD budget, the
    ensemble must not emit BUY here.
    """

    @pytest.fixture
    def declining(self, frame_factory):
        df = frame_factory(300, seed=3, end_multiplier=0.28)
        close = df["close"]
        # A mild dead-cat bounce: enough to flip the histogram, not the line.
        bounce = close.iloc[-5] * np.array([1.012, 1.022, 1.030, 1.038])
        close.iloc[-4:] = bounce
        df["close"] = close
        df["high"] = close * 1.015
        df["low"] = close * 0.985
        return df

    def test_the_setup_is_the_one_described(self, declining):
        fs = extract_features("FALL", declining)
        total_return = declining["close"].iloc[-1] / declining["close"].iloc[0] - 1
        assert total_return < -0.60, "this fixture must be a severe decline"
        assert fs.values["macd_line"] < 0, "the LINE must still be bearish"
        assert fs.values["macd_hist_pct"] > 0, "the HISTOGRAM must look bullish"

    def test_histogram_alone_would_say_bullish(self, declining):
        sig = score_featureset(extract_features("FALL", declining))
        assert sig.feature_scores["macd_hist_pct"] > 0.3

    def test_but_the_ensemble_does_not_say_buy(self, declining):
        sig = score_featureset(extract_features("FALL", declining))
        assert sig.action != "BUY", (
            f"a sustained decline must not read BULLISH; got {sig.action} "
            f"at composite {sig.composite:+.3f}"
        )
        assert sig.feature_scores["macd_line"] < 0
        assert sig.dimension_scores["trend"] < 0

    def test_the_same_decline_without_a_bounce_is_a_sell(self, frame_factory):
        df = frame_factory(300, seed=3, end_multiplier=0.28)
        sig = score_featureset(extract_features("FALL", df))
        assert sig.action == "SELL"
        assert sig.conviction in {"HIGH", "VERY_HIGH"}


class TestEnsembleBehaviour:
    def test_sustained_uptrend_is_a_buy(self, frame_factory):
        sig = score_featureset(extract_features("UP", frame_factory(300, seed=3, end_multiplier=2.5)))
        assert sig.action == "BUY"
        assert sig.dimension_scores["trend"] > 0.5

    def test_flat_market_is_a_hold(self, frame_factory):
        sig = score_featureset(extract_features("FLAT", frame_factory(300, seed=3, end_multiplier=1.0)))
        assert sig.action == "HOLD"

    def test_composite_is_bounded(self, frame_factory):
        for seed in range(6):
            sig = score_featureset(extract_features("X", frame_factory(300, seed=seed)))
            assert -1.0 <= sig.composite <= 1.0

    def test_sentiment_moves_the_composite_in_the_right_direction(self, frame_factory):
        fs = extract_features("X", frame_factory(300, seed=11))
        up = score_featureset(fs, sentiment=1.0).composite
        down = score_featureset(fs, sentiment=-1.0).composite
        assert up > down

    def test_sentiment_cannot_dominate_the_technicals(self, frame_factory):
        """Sentiment is 10% of the composite; it must not flip a strong SELL."""
        fs = extract_features("FALL", frame_factory(300, seed=3, end_multiplier=0.28))
        assert score_featureset(fs, sentiment=1.0).action == "SELL"

    def test_conviction_rises_with_the_absolute_score(self, frame_factory):
        strong = score_featureset(extract_features("UP", frame_factory(300, seed=3, end_multiplier=3.0)))
        weak = score_featureset(extract_features("FLAT", frame_factory(300, seed=3, end_multiplier=1.0)))
        order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}
        assert order[strong.conviction] > order[weak.conviction]

    def test_scoring_is_deterministic(self, frame_factory):
        df = frame_factory(300, seed=12)
        a = score_featureset(extract_features("X", df)).to_dict()
        b = score_featureset(extract_features("X", df)).to_dict()
        assert a == b

    def test_rationale_explains_the_macd_split(self, frame_factory):
        sig = score_featureset(extract_features("X", frame_factory(300, seed=13)))
        assert any("MACD line" in line for line in sig.rationale)

    def test_nan_features_score_neutral_not_crash(self, frame_factory):
        fs = extract_features("SHORT", frame_factory(35, seed=14))
        sig = score_featureset(fs)
        assert sig.action in {"BUY", "SELL", "HOLD"}
        assert -1.0 <= sig.composite <= 1.0
