"""Raw feature extraction: an OHLCV frame in, 28 named numbers out.

Features are grouped into the five dimensions the strategy brief asks for.
``extract_features`` returns plain floats for the most recent bar so the result
is JSON-serialisable and can cross the MCP boundary unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from . import indicators as ind

TREND = "trend"
MOMENTUM = "momentum"
VOLUME = "volume"
VOLATILITY = "volatility"
STATISTICS = "statistics"

DIMENSIONS: List[str] = [TREND, MOMENTUM, VOLUME, VOLATILITY, STATISTICS]

#: Minimum bars needed before the slowest feature (EMA200, 60-bar skew) is real.
MIN_BARS = 220

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass
class FeatureSet:
    """Features for one symbol at one point in time."""

    symbol: str
    as_of: str
    close: float
    values: Dict[str, float] = field(default_factory=dict)
    #: Numbers the pipeline needs but does NOT score — ATR for stop sizing,
    #: beta for position sizing, the raw opening range. Keeping them out of
    #: ``values`` means the scored-feature count stays honest.
    diagnostics: Dict[str, float] = field(default_factory=dict)
    dimension_of: Dict[str, str] = field(default_factory=dict)
    bars_available: int = 0
    warnings: List[str] = field(default_factory=list)

    def by_dimension(self, dimension: str) -> Dict[str, float]:
        return {
            k: v for k, v in self.values.items() if self.dimension_of.get(k) == dimension
        }

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "close": self.close,
            "bars_available": self.bars_available,
            "features": self.values,
            "diagnostics": self.diagnostics,
            "dimensions": self.dimension_of,
            "warnings": self.warnings,
        }


def _f(x) -> float:
    """Coerce to a finite float, or NaN."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v if np.isfinite(v) else float("nan")


def _last(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return float("nan")
    return _f(series.iloc[-1])


def _pct_rel(value: float, reference: float) -> float:
    """Percent distance of `value` above `reference`."""
    if not np.isfinite(value) or not np.isfinite(reference) or reference == 0:
        return float("nan")
    return 100.0 * (value / reference - 1.0)


def _slope_pct(series: pd.Series, lookback: int) -> float:
    """Percent change of a series over `lookback` bars (sign = direction)."""
    s = series.dropna()
    if len(s) <= lookback:
        return float("nan")
    prev, cur = _f(s.iloc[-1 - lookback]), _f(s.iloc[-1])
    if not np.isfinite(prev) or prev == 0:
        return float("nan")
    return 100.0 * (cur / prev - 1.0)


def normalise_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case the columns, sort by time, drop duplicate timestamps."""
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV frame is missing columns: {missing}")
    if not isinstance(out.index, pd.DatetimeIndex):
        for cand in ("timestamp", "time", "date"):
            if cand in out.columns:
                out = out.set_index(pd.to_datetime(out[cand], utc=True))
                break
    out = out[~out.index.duplicated(keep="last")].sort_index()
    for col in REQUIRED_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["close"])


def extract_features(
    symbol: str,
    df: pd.DataFrame,
    benchmarks: Optional[Mapping[str, pd.DataFrame]] = None,
    intraday: Optional[pd.DataFrame] = None,
) -> FeatureSet:
    """Compute the full feature vector for the latest bar of `df`.

    ``benchmarks`` maps a ticker (SPY, QQQ) to its daily frame and powers the
    relative-strength and beta features. ``intraday`` is a 15-minute frame for
    the same symbol and powers the opening-range and relative-volume
    features. Both are optional: without them those features are NaN, which
    the scorer treats as neutral rather than as a reason to fail.
    """
    data = normalise_frame(df)
    o, h, l, c, v = (data[k] for k in REQUIRED_COLUMNS)
    n = len(data)
    as_of = str(data.index[-1]) if n else ""
    fs = FeatureSet(symbol=symbol, as_of=as_of, close=_last(c), bars_available=n)
    if n < 30:
        fs.warnings.append(
            f"only {n} bars available; most features need {MIN_BARS} for full fidelity"
        )
    elif n < MIN_BARS:
        fs.warnings.append(
            f"{n} bars available; EMA200 and 60-bar statistics are not yet seeded"
        )

    def put(name: str, dimension: str, value: float) -> None:
        fs.values[name] = _f(value)
        fs.dimension_of[name] = dimension

    def diag(name: str, value: float) -> None:
        """Record a number the pipeline needs but that is not scored."""
        fs.diagnostics[name] = _f(value)

    price = _last(c)

    # ---------------- TREND (7) ----------------
    ema20, ema50, ema200 = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    put("ema20_rel", TREND, _pct_rel(price, _last(ema20)))
    put("ema50_rel", TREND, _pct_rel(price, _last(ema50)))
    put("ema200_rel", TREND, _pct_rel(price, _last(ema200)))
    put("ema20_50_spread", TREND, _pct_rel(_last(ema20), _last(ema50)))
    put("ema50_200_spread", TREND, _pct_rel(_last(ema50), _last(ema200)))
    adx_df = ind.adx(h, l, c, 14)
    adx_val = _last(adx_df["adx"])
    di_bias = _last(adx_df["plus_di"]) - _last(adx_df["minus_di"])
    put("adx", TREND, adx_val)
    put("di_bias", TREND, di_bias)
    macd_df = ind.macd(c)
    # The MACD LINE versus zero is the trend statement.
    put("macd_line", TREND, _last(macd_df["macd"]))

    # ---------------- MOMENTUM (5) ----------------
    put("rsi14", MOMENTUM, _last(ind.rsi(c, 14)))
    # The HISTOGRAM is the momentum statement.  Normalised by price so it is
    # comparable across a $9 stock and a $900 one.
    hist = _last(macd_df["hist"])
    put("macd_hist_pct", MOMENTUM, 100.0 * hist / price if price else float("nan"))
    put("roc12", MOMENTUM, _last(ind.roc(c, 12)))
    put("tsi", MOMENTUM, _last(ind.tsi(c)))
    # Relative strength: the stock's 20-day return minus the benchmark's.
    # Positive means it outpaced the market. Without this every feature above
    # would happily buy a stock up 3% on a day the market rose 4%.
    marks = {k.upper(): v for k, v in (benchmarks or {}).items()}
    for bench, feature in (("SPY", "rs_spy20"), ("QQQ", "rs_qqq20")):
        frame = marks.get(bench)
        if frame is None or "close" in getattr(frame, "columns", []) is False:
            put(feature, MOMENTUM, float("nan"))
            continue
        try:
            put(feature, MOMENTUM, _last(ind.relative_strength(c, frame["close"], 20)))
        except Exception:
            put(feature, MOMENTUM, float("nan"))

    # ---------------- VOLUME (5) ----------------
    put("cmf20", VOLUME, _last(ind.cmf(h, l, c, v, 20)))
    obv_series = ind.obv(c, v)
    put("obv_slope20", VOLUME, _slope_pct(obv_series.abs().replace(0.0, np.nan), 20))
    put("mfi14", VOLUME, _last(ind.mfi(h, l, c, v, 14)))
    # Relative volume against the same point in prior sessions. On the free
    # IEX feed this sees only a slice of consolidated volume, so it is scored
    # as a weak confirmation and never used as a hard gate.
    put("rvol", VOLUME, ind.relative_volume(intraday) if intraday is not None else float("nan"))

    # ---------------- VOLATILITY (6) ----------------
    atr_series = ind.atr(h, l, c, 14)
    # ATR is needed for stop sizing but carries no direction, so it is a
    # diagnostic rather than a scored feature.
    diag("atr14", _last(atr_series))
    natr_series = ind.natr(h, l, c, 14)
    put("natr14", VOLATILITY, _last(natr_series))
    put("natr_z60", VOLATILITY, _last(ind.zscore(natr_series, 60)))
    bb = ind.bollinger(c, 20, 2.0)
    put("bb_width", VOLATILITY, _last(bb["width"]))
    put("bb_pct_b", VOLATILITY, _last(bb["pct_b"]))
    put("donchian_pos20", VOLATILITY, _last(ind.donchian(h, l, c, 20)["position"]))
    # Opening-range position: 0 at the range low, 1 at the high, above 1 is an
    # upside breakout. Needs intraday bars; NaN (neutral) without them.
    orb = ind.opening_range(intraday, bars=1) if intraday is not None else {}
    put("orb_pos", VOLATILITY, orb.get("position", float("nan")))
    diag("orb_high", orb.get("high", float("nan")))
    diag("orb_low", orb.get("low", float("nan")))
    if intraday is not None and not intraday.empty:
        # ATR on the intraday frame, for tighter bracket stops than the daily
        # ATR would give.
        diag("atr_intraday", _last(ind.atr(
            intraday["high"], intraday["low"], intraday["close"], 14)))

    # ---------------- STATISTICS (5) ----------------
    put("zscore20", STATISTICS, _last(ind.zscore(c, 20)))
    put("ret5", STATISTICS, _last(ind.trailing_return(c, 5)))
    put("ret20", STATISTICS, _last(ind.trailing_return(c, 20)))
    put("ret60", STATISTICS, _last(ind.trailing_return(c, 60)))
    put("skew60", STATISTICS, _last(ind.rolling_skew(c, 60)))
    # Beta against SPY: scored (low beta is mildly preferred for a given
    # signal strength) and also used by the risk module to size down the
    # jumpier names and by the alpha report for Jensen's alpha.
    spy = marks.get("SPY")
    beta = float("nan")
    if spy is not None:
        try:
            beta = _last(ind.rolling_beta(c, spy["close"], 60))
        except Exception:
            beta = float("nan")
    put("beta60", STATISTICS, beta)
    diag("beta60", beta)

    return fs


def feature_count() -> int:
    """Number of features the extractor produces (used by tests and the README)."""
    idx = pd.date_range("2024-01-01", periods=MIN_BARS + 40, freq="B", tz="UTC")
    rng = np.random.default_rng(7)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.02, len(idx))), index=idx)
    frame = pd.DataFrame(
        {
            "open": close.shift(1).bfill(),
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, len(idx)).astype(float),
        }
    )
    return len(extract_features("TEST", frame).values)
