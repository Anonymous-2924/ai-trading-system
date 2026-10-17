"""Raw feature extraction: an OHLCV frame in, 28 named numbers out.

Features are grouped into the five dimensions the strategy brief asks for.
``extract_features`` returns plain floats for the most recent bar so the result
is JSON-serialisable and can cross the MCP boundary unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

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


def extract_features(symbol: str, df: pd.DataFrame) -> FeatureSet:
    """Compute the full feature vector for the latest bar of `df`."""
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
    put("roc5", MOMENTUM, _last(ind.roc(c, 5)))
    put("tsi", MOMENTUM, _last(ind.tsi(c)))

    # ---------------- VOLUME (5) ----------------
    put("cmf20", VOLUME, _last(ind.cmf(h, l, c, v, 20)))
    obv_series = ind.obv(c, v)
    put("obv_slope20", VOLUME, _slope_pct(obv_series.abs().replace(0.0, np.nan), 20))
    put("mfi14", VOLUME, _last(ind.mfi(h, l, c, v, 14)))
    put("pvo", VOLUME, _last(ind.pvo(v)["pvo"]))
    put("volume_z20", VOLUME, _last(ind.zscore(v, 20)))

    # ---------------- VOLATILITY (6) ----------------
    atr_series = ind.atr(h, l, c, 14)
    put("atr14", VOLATILITY, _last(atr_series))
    natr_series = ind.natr(h, l, c, 14)
    put("natr14", VOLATILITY, _last(natr_series))
    put("natr_z60", VOLATILITY, _last(ind.zscore(natr_series, 60)))
    bb = ind.bollinger(c, 20, 2.0)
    put("bb_width", VOLATILITY, _last(bb["width"]))
    put("bb_pct_b", VOLATILITY, _last(bb["pct_b"]))
    put("donchian_pos20", VOLATILITY, _last(ind.donchian(h, l, c, 20)["position"]))

    # ---------------- STATISTICS (5) ----------------
    put("zscore20", STATISTICS, _last(ind.zscore(c, 20)))
    put("ret5", STATISTICS, _last(ind.trailing_return(c, 5)))
    put("ret20", STATISTICS, _last(ind.trailing_return(c, 20)))
    put("ret60", STATISTICS, _last(ind.trailing_return(c, 60)))
    put("skew60", STATISTICS, _last(ind.rolling_skew(c, 60)))

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
