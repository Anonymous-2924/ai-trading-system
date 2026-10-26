"""Weighted ensemble: 29 raw features -> one composite score -> BUY/SELL/HOLD.

Every feature is mapped to a sub-score in [-1, +1] where +1 is maximally
bullish.  Sub-scores are averaged inside their dimension, dimensions are
combined with configurable weights, and news sentiment enters as a sixth
weighted input.

MACD
----
The MACD *line* versus zero is a TREND statement and the *histogram* is a
MOMENTUM statement.  They are weighted 60/40 in favour of the line.  This
matters: during a sustained decline the histogram turns positive on every
bounce, so scoring the histogram alone makes a 72% drawdown read BULLISH.
``macd_effective_weights()`` derives the per-dimension slots from the budget
so the 60/40 split survives dimension re-weighting; ``tests/test_scoring.py``
asserts both the ratio and the 72%-decline case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from .features import (
    DIMENSIONS,
    MOMENTUM,
    STATISTICS,
    TREND,
    VOLATILITY,
    VOLUME,
    FeatureSet,
)

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"

#: Default weight of each dimension in the composite.  Sums to 1.0 with
#: ``sentiment``.  Trend and momentum dominate: the brief asks for an
#: aggressive momentum/growth posture, not mean reversion.
DEFAULT_DIMENSION_WEIGHTS: Dict[str, float] = {
    TREND: 0.28,
    MOMENTUM: 0.24,
    VOLUME: 0.14,
    VOLATILITY: 0.12,
    STATISTICS: 0.12,
    "sentiment": 0.10,
}

#: Share of the whole composite that MACD is allowed to claim, and how that
#: share splits between its trend half and its momentum half.
MACD_BUDGET = 0.10
MACD_TREND_SHARE = 0.60
MACD_MOMENTUM_SHARE = 0.40

#: Relative weights of the non-MACD features inside each dimension.  They are
#: rescaled at runtime to fill whatever MACD does not take.
BASE_FEATURE_WEIGHTS: Dict[str, float] = {
    # trend
    "ema20_rel": 0.18,
    "ema50_rel": 0.16,
    "ema200_rel": 0.20,
    "ema20_50_spread": 0.14,
    "ema50_200_spread": 0.14,
    "adx": 0.08,
    "di_bias": 0.10,
    # momentum  (relative strength carries real weight: it is the only thing
    # here that compares the stock with the market rather than with itself)
    "rsi14": 0.20,
    "roc12": 0.18,
    "tsi": 0.20,
    "rs_spy20": 0.25,
    "rs_qqq20": 0.17,
    # volume  (rvol is deliberately light: on the free IEX feed it sees only a
    # slice of consolidated volume, so it confirms rather than decides)
    "cmf20": 0.35,
    "obv_slope20": 0.22,
    "mfi14": 0.28,
    "rvol": 0.15,
    # volatility
    "natr14": 0.16,
    "natr_z60": 0.16,
    "bb_width": 0.14,
    "bb_pct_b": 0.22,
    "donchian_pos20": 0.17,
    "orb_pos": 0.15,
    # statistics
    "zscore20": 0.18,
    "ret5": 0.12,
    "ret20": 0.26,
    "ret60": 0.22,
    "skew60": 0.10,
    "beta60": 0.12,
}

MACD_FEATURES = {"macd_line": TREND, "macd_hist_pct": MOMENTUM}


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _squash(value: float, scale: float) -> float:
    """Map an unbounded value onto [-1, 1] smoothly.  `scale` is the value that
    maps to roughly +0.76 (tanh(1))."""
    if value is None or not math.isfinite(value) or scale == 0:
        return 0.0
    return clamp(math.tanh(value / scale))


def _centred(value: float, centre: float, scale: float) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return _squash(value - centre, scale)


def _tent(value: float, low: float, high: float, over: float) -> float:
    """Reward a value inside [low, high], punish once it exceeds `over`.

    Used for band positions, where "near the top" is a breakout but "far
    outside the top" is an exhausted move.
    """
    if value is None or not math.isfinite(value):
        return 0.0
    if value >= over:
        return clamp(1.0 - 2.0 * (value - over) / max(over - high, 1e-9))
    span = high - low
    if span <= 0:
        return 0.0
    return clamp(2.0 * (value - low) / span - 1.0)


# --------------------------------------------------------------------------
# Per-feature scorers.  Each returns a sub-score in [-1, +1].
# --------------------------------------------------------------------------
def _score_feature(name: str, value: float, fs: Optional[FeatureSet] = None) -> float:
    if value is None or not math.isfinite(value):
        return 0.0

    # --- trend -------------------------------------------------------------
    if name == "ema20_rel":
        return _squash(value, 3.0)
    if name == "ema50_rel":
        return _squash(value, 6.0)
    if name == "ema200_rel":
        return _squash(value, 15.0)
    if name == "ema20_50_spread":
        return _squash(value, 3.0)
    if name == "ema50_200_spread":
        return _squash(value, 8.0)
    if name == "adx":
        # ADX is unsigned: it says how strong the trend is, not which way.
        # Direction comes from di_bias; here a strong trend simply amplifies
        # whatever the rest of the trend block says, so we score it against
        # the directional bias we already have.
        bias = 0.0
        if fs is not None:
            raw_bias = fs.values.get("di_bias", 0.0)
            bias = _squash(raw_bias, 12.0) if math.isfinite(raw_bias or float("nan")) else 0.0
        strength = clamp((value - 20.0) / 20.0, 0.0, 1.0)
        return clamp(bias * strength)
    if name == "di_bias":
        return _squash(value, 12.0)
    if name == "macd_line":
        # Position versus ZERO — this is the trend half of MACD.
        return _squash(value, 1.5)

    # --- momentum ----------------------------------------------------------
    if name == "rsi14":
        # Momentum regime, not mean reversion: 50 is neutral, 70+ is strong.
        # Only a genuinely parabolic >85 starts to subtract.
        if value >= 85.0:
            return clamp(1.0 - (value - 85.0) / 10.0)
        return _centred(value, 50.0, 18.0)
    if name == "macd_hist_pct":
        return _squash(value, 0.6)
    if name == "roc12":
        return _squash(value, 8.0)
    if name == "roc5":
        return _squash(value, 4.0)
    if name == "tsi":
        return _squash(value, 25.0)
    if name in ("rs_spy20", "rs_qqq20"):
        # Percent outperformance of the benchmark over 20 days. +5% is a
        # strong relative-strength reading; -5% means the market carried it.
        return _squash(value, 5.0)

    # --- volume ------------------------------------------------------------
    if name == "cmf20":
        return _squash(value, 0.12)
    if name == "obv_slope20":
        return _squash(value, 12.0)
    if name == "mfi14":
        if value >= 90.0:
            return clamp(1.0 - (value - 90.0) / 7.0)
        return _centred(value, 50.0, 20.0)
    if name == "pvo":
        # Rising participation confirms whatever the price is doing; on its own
        # it is weakly bullish.
        return _squash(value, 25.0)
    if name == "rvol":
        # 1.0 is a normal session. Heavy participation confirms a move;
        # a very quiet tape is mildly discouraging. Capped tightly because
        # the underlying data is only a slice of real volume.
        if not math.isfinite(value) or value <= 0:
            return 0.0
        return clamp(_squash(value - 1.0, 1.5), -0.6, 0.6)

    # --- volatility --------------------------------------------------------
    if name == "atr14":
        # Absolute ATR carries no direction and no cross-symbol meaning; it is
        # kept as a feature because risk sizing uses it, but it scores neutral.
        return 0.0
    if name == "natr14":
        # An aggressive mandate wants movement, but above ~9% daily range the
        # position sizing starts to hurt more than the move helps.
        return clamp(_tent(value, 0.5, 5.0, 9.0))
    if name == "natr_z60":
        # Volatility far above its own recent regime is a warning.
        return clamp(-_squash(value - 1.0, 1.5)) if value > 1.0 else 0.0
    if name == "bb_width":
        # Expansion is good when price is in the upper half of the band.
        pct_b = 0.5
        if fs is not None:
            raw = fs.values.get("bb_pct_b")
            if raw is not None and math.isfinite(raw):
                pct_b = raw
        direction = clamp((pct_b - 0.5) * 2.0)
        return clamp(direction * _squash(value, 0.14))
    if name == "bb_pct_b":
        return _tent(value, 0.0, 1.0, 1.15)
    if name == "donchian_pos20":
        return _tent(value, 0.0, 1.0, 1.10)
    if name == "orb_pos":
        # Opening-range breakout: above 1 the stock has cleared its first
        # 15 minutes. Past 1.5 the move is extended and we stop adding credit.
        return _tent(value, 0.0, 1.0, 1.50)

    # --- statistics --------------------------------------------------------
    if name == "zscore20":
        # Trend-following read: extension above the mean is strength until it
        # is extreme (>3 sigma), where it is a blow-off.
        if value > 3.0:
            return clamp(1.0 - (value - 3.0))
        return _squash(value, 1.6)
    if name == "ret5":
        return _squash(value, 5.0)
    if name == "ret20":
        return _squash(value, 10.0)
    if name == "ret60":
        return _squash(value, 20.0)
    if name == "beta60":
        # The mandate WANTS high-beta exposure, so beta is near-neutral here
        # and only penalised once it is genuinely extreme. Beta's real job in
        # this system is position sizing (risk.py), not signal generation.
        if not math.isfinite(value):
            return 0.0
        if value > 2.0:
            return clamp(-(value - 2.0) / 1.5, -1.0, 0.0)
        return 0.0
    if name == "skew60":
        # Positive skew = occasional large up-days, which is exactly the
        # payoff profile a high-beta growth sleeve is buying.
        return _squash(value, 1.0)

    return 0.0


def macd_effective_weights(
    dimension_weights: Mapping[str, float] = None,
    budget: float = MACD_BUDGET,
) -> Dict[str, float]:
    """In-dimension weights for the MACD slots that preserve the 60/40 split.

    ``budget`` is MACD's share of the whole composite.  Dividing by the
    dimension weight converts that share into an in-dimension weight, so the
    split survives any re-weighting of the dimensions themselves.
    """
    dw = dict(dimension_weights or DEFAULT_DIMENSION_WEIGHTS)
    trend_w = dw.get(TREND, DEFAULT_DIMENSION_WEIGHTS[TREND]) or 1e-9
    mom_w = dw.get(MOMENTUM, DEFAULT_DIMENSION_WEIGHTS[MOMENTUM]) or 1e-9
    return {
        "macd_line": min(0.9, budget * MACD_TREND_SHARE / trend_w),
        "macd_hist_pct": min(0.9, budget * MACD_MOMENTUM_SHARE / mom_w),
    }


def unweighted_features() -> List[str]:
    """Scored features that carry no weight — they would be silently ignored.

    Adding a feature to ``features.py`` without adding it here is an easy and
    invisible mistake: the feature is computed, shown in the artefacts, and
    contributes nothing. A test asserts this list stays empty.
    """
    dim_of = _dimension_lookup()
    known = set(BASE_FEATURE_WEIGHTS) | set(MACD_FEATURES)
    return sorted(name for name in dim_of if name not in known)


def feature_weights(
    dimension_weights: Mapping[str, float] = None, budget: float = MACD_BUDGET
) -> Dict[str, Dict[str, float]]:
    """Per-dimension feature weights, each dimension summing to 1.0."""
    macd_slots = macd_effective_weights(dimension_weights, budget)
    out: Dict[str, Dict[str, float]] = {d: {} for d in DIMENSIONS}
    from .features import extract_features  # noqa: F401  (import kept local)

    dim_of = _dimension_lookup()
    for dim in DIMENSIONS:
        reserved = sum(w for n, w in macd_slots.items() if MACD_FEATURES[n] == dim)
        others = {
            n: w
            for n, w in BASE_FEATURE_WEIGHTS.items()
            if dim_of.get(n) == dim and n not in MACD_FEATURES
        }
        total = sum(others.values()) or 1.0
        scale = (1.0 - reserved) / total
        out[dim] = {n: w * scale for n, w in others.items()}
        for n, w in macd_slots.items():
            if MACD_FEATURES[n] == dim:
                out[dim][n] = w
    return out


_DIM_LOOKUP: Optional[Dict[str, str]] = None


def _dimension_lookup() -> Dict[str, str]:
    """Map feature name -> dimension, derived once from the extractor itself so
    the two modules cannot drift apart."""
    global _DIM_LOOKUP
    if _DIM_LOOKUP is None:
        import numpy as np
        import pandas as pd

        from .features import extract_features

        idx = pd.date_range("2024-01-01", periods=260, freq="B", tz="UTC")
        rng = np.random.default_rng(1)
        close = pd.Series(
            100 * np.cumprod(1 + rng.normal(0.0005, 0.015, len(idx))), index=idx
        )
        frame = pd.DataFrame(
            {
                "open": close.shift(1).bfill(),
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": rng.integers(1_000_000, 4_000_000, len(idx)).astype(float),
            }
        )
        _DIM_LOOKUP = dict(extract_features("WEIGHTS", frame).dimension_of)
    return dict(_DIM_LOOKUP)


@dataclass
class Signal:
    symbol: str
    action: str
    composite: float
    conviction: str
    conviction_score: float
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    feature_scores: Dict[str, float] = field(default_factory=dict)
    sentiment_score: float = 0.0
    rationale: List[str] = field(default_factory=list)
    close: float = float("nan")
    as_of: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "composite": round(self.composite, 4),
            "conviction": self.conviction,
            "conviction_score": round(self.conviction_score, 4),
            "dimension_scores": {k: round(v, 4) for k, v in self.dimension_scores.items()},
            "feature_scores": {k: round(v, 4) for k, v in self.feature_scores.items()},
            "sentiment_score": round(self.sentiment_score, 4),
            "close": self.close,
            "as_of": self.as_of,
            "rationale": self.rationale,
        }


def conviction_from(score: float, thresholds: Mapping[str, float]) -> str:
    a = abs(score)
    if a >= thresholds.get("very_high", 0.55):
        return "VERY_HIGH"
    if a >= thresholds.get("high", 0.38):
        return "HIGH"
    if a >= thresholds.get("medium", 0.22):
        return "MEDIUM"
    return "LOW"


def score_featureset(
    fs: FeatureSet,
    sentiment: float = 0.0,
    dimension_weights: Mapping[str, float] = None,
    buy_threshold: float = 0.18,
    sell_threshold: float = -0.18,
    conviction_thresholds: Mapping[str, float] = None,
    macd_budget: float = MACD_BUDGET,
) -> Signal:
    """Collapse a FeatureSet (+ sentiment in [-1, 1]) into one Signal."""
    dw = dict(DEFAULT_DIMENSION_WEIGHTS)
    if dimension_weights:
        dw.update(dimension_weights)
    weights = feature_weights(dw, macd_budget)

    feature_scores: Dict[str, float] = {}
    dim_scores: Dict[str, float] = {}
    for dim in DIMENSIONS:
        total_w = 0.0
        acc = 0.0
        for name, w in weights[dim].items():
            raw = fs.values.get(name)
            s = _score_feature(name, raw, fs)
            feature_scores[name] = s
            acc += w * s
            total_w += w
        dim_scores[dim] = acc / total_w if total_w else 0.0

    sentiment = clamp(float(sentiment or 0.0))
    composite = sum(dw.get(d, 0.0) * dim_scores[d] for d in DIMENSIONS)
    composite += dw.get("sentiment", 0.0) * sentiment
    weight_total = sum(dw.get(d, 0.0) for d in DIMENSIONS) + dw.get("sentiment", 0.0)
    if weight_total:
        composite /= weight_total
    composite = clamp(composite)

    if composite >= buy_threshold:
        action = BUY
    elif composite <= sell_threshold:
        action = SELL
    else:
        action = HOLD

    conviction = conviction_from(composite, conviction_thresholds or {})
    rationale = _build_rationale(fs, dim_scores, feature_scores, sentiment, action)

    return Signal(
        symbol=fs.symbol,
        action=action,
        composite=composite,
        conviction=conviction,
        conviction_score=abs(composite),
        dimension_scores=dim_scores,
        feature_scores=feature_scores,
        sentiment_score=sentiment,
        rationale=rationale,
        close=fs.close,
        as_of=fs.as_of,
    )


def _build_rationale(
    fs: FeatureSet,
    dim_scores: Mapping[str, float],
    feature_scores: Mapping[str, float],
    sentiment: float,
    action: str,
) -> List[str]:
    lines = [
        f"{action}: "
        + ", ".join(f"{d}={dim_scores[d]:+.2f}" for d in DIMENSIONS)
        + f", sentiment={sentiment:+.2f}"
    ]
    ranked = sorted(feature_scores.items(), key=lambda kv: -abs(kv[1]))[:5]
    for name, s in ranked:
        raw = fs.values.get(name)
        raw_txt = "n/a" if raw is None or not math.isfinite(raw) else f"{raw:.3f}"
        lines.append(f"  {name}={raw_txt} -> {s:+.2f}")
    macd_line = fs.values.get("macd_line", float("nan"))
    if math.isfinite(macd_line):
        side = "above" if macd_line > 0 else "below"
        lines.append(
            f"  MACD line {macd_line:+.3f} is {side} zero (trend, 60% of the MACD "
            f"budget); histogram contributes the remaining 40%"
        )
    if fs.warnings:
        lines.extend(f"  warning: {w}" for w in fs.warnings)
    return lines
