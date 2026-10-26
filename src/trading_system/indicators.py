"""Technical indicators implemented directly in pandas/numpy.

Deliberately dependency-free beyond pandas and numpy.  ``pandas_ta`` is NOT
used: it breaks against numpy 2.x (it imports ``numpy.NaN``, removed in 2.0).

Smoothing conventions
---------------------
RSI, ATR and ADX use *Wilder's* smoothing seeded with a simple moving average
of the first ``period`` observations:

    seed      = mean(x[0:period])
    s[t]      = s[t-1] + (x[t] - s[t-1]) / period

This is NOT the same as ``Series.ewm(alpha=1/period, adjust=False)``, which
seeds with the first observation alone and therefore disagrees with every
charting package for the first few hundred bars.  ``tests/test_indicators.py``
checks these against hand calculations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "wilder_smooth",
    "sma",
    "ema",
    "rsi",
    "true_range",
    "atr",
    "natr",
    "adx",
    "macd",
    "roc",
    "tsi",
    "cmf",
    "obv",
    "mfi",
    "pvo",
    "bollinger",
    "donchian",
    "zscore",
    "trailing_return",
    "rolling_skew",
]


def _as_series(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x.astype("float64")
    return pd.Series(np.asarray(x, dtype="float64"))


def wilder_smooth(values, period: int) -> pd.Series:
    """Wilder's recursive smoothing, seeded with the SMA of the first `period`.

    Output is NaN until index ``period - 1``, where it equals the seed SMA.
    """
    s = _as_series(values)
    if period <= 0:
        raise ValueError("period must be positive")
    arr = s.to_numpy(dtype="float64", copy=True)
    n = arr.size
    out = np.full(n, np.nan, dtype="float64")
    if n < period:
        return pd.Series(out, index=s.index)

    # The seed window must be clean; a NaN inside it poisons the whole series,
    # so we start at the first index where `period` consecutive values exist.
    start = None
    run = 0
    for i in range(n):
        run = run + 1 if np.isfinite(arr[i]) else 0
        if run == period:
            start = i
            break
    if start is None:
        return pd.Series(out, index=s.index)

    prev = float(np.mean(arr[start - period + 1 : start + 1]))
    out[start] = prev
    for i in range(start + 1, n):
        x = arr[i]
        if not np.isfinite(x):
            x = prev  # a gap holds the level rather than destroying the series
        prev = prev + (x - prev) / period
        out[i] = prev
    return pd.Series(out, index=s.index)


def sma(values, period: int) -> pd.Series:
    return _as_series(values).rolling(period, min_periods=period).mean()


def ema(values, period: int) -> pd.Series:
    """SMA-seeded exponential moving average (the charting-package convention)."""
    s = _as_series(values)
    arr = s.to_numpy(dtype="float64", copy=True)
    n = arr.size
    out = np.full(n, np.nan, dtype="float64")
    if n < period:
        return pd.Series(out, index=s.index)
    alpha = 2.0 / (period + 1.0)
    prev = float(np.mean(arr[:period]))
    out[period - 1] = prev
    for i in range(period, n):
        x = arr[i]
        if not np.isfinite(x):
            x = prev
        prev = prev + alpha * (x - prev)
        out[i] = prev
    return pd.Series(out, index=s.index)


def rsi(close, period: int = 14) -> pd.Series:
    """Wilder's RSI.  100 when there are no losses in the window."""
    c = _as_series(close)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # diff() produces NaN at index 0; drop it from the seed window.
    avg_gain = wilder_smooth(gain.iloc[1:], period)
    avg_loss = wilder_smooth(loss.iloc[1:], period)
    avg_gain = avg_gain.reindex(c.index)
    avg_loss = avg_loss.reindex(c.index)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 with a positive avg_gain is a pure uptrend -> RSI 100.
    out = out.where(~((avg_loss == 0.0) & (avg_gain > 0.0)), 100.0)
    out = out.where(~((avg_loss == 0.0) & (avg_gain == 0.0)), 50.0)
    return out


def true_range(high, low, close) -> pd.Series:
    h, l, c = _as_series(high), _as_series(low), _as_series(close)
    prev_close = c.shift(1)
    tr = pd.concat(
        [(h - l).abs(), (h - prev_close).abs(), (l - prev_close).abs()], axis=1
    ).max(axis=1)
    tr.iloc[0] = float(h.iloc[0] - l.iloc[0]) if len(h) else np.nan
    return tr


def atr(high, low, close, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    tr = true_range(high, low, close)
    return wilder_smooth(tr, period)


def natr(high, low, close, period: int = 14) -> pd.Series:
    """Normalised ATR, in percent of price."""
    c = _as_series(close)
    a = atr(high, low, close, period)
    return 100.0 * a / c.replace(0.0, np.nan)


def adx(high, low, close, period: int = 14) -> pd.DataFrame:
    """Wilder's ADX with +DI / -DI.  Returns columns adx, plus_di, minus_di."""
    h, l, c = _as_series(high), _as_series(low), _as_series(close)
    up_move = h.diff()
    down_move = -l.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move.fillna(0.0), 0.0),
        index=h.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move.fillna(0.0), 0.0),
        index=h.index,
    )
    tr = true_range(h, l, c)

    # Index 0 has no previous bar, so no directional movement is defined.
    sm_tr = wilder_smooth(tr.iloc[1:], period).reindex(h.index)
    sm_plus = wilder_smooth(plus_dm.iloc[1:], period).reindex(h.index)
    sm_minus = wilder_smooth(minus_dm.iloc[1:], period).reindex(h.index)

    denom = sm_tr.replace(0.0, np.nan)
    plus_di = 100.0 * sm_plus / denom
    minus_di = 100.0 * sm_minus / denom
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx_line = wilder_smooth(dx.dropna(), period).reindex(h.index)
    return pd.DataFrame(
        {"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di}, index=h.index
    )


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD.  Columns: macd (the line), signal, hist.

    The LINE's position versus zero is a TREND statement; the HISTOGRAM
    (line minus signal) is a MOMENTUM statement.  They disagree often and the
    scoring layer weights them 60/40 — see ``scoring.py``.
    """
    c = _as_series(close)
    line = ema(c, fast) - ema(c, slow)
    sig = ema(line.dropna(), signal).reindex(c.index)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig}, index=c.index)


def roc(close, period: int = 12) -> pd.Series:
    """Rate of change, percent."""
    c = _as_series(close)
    return 100.0 * (c / c.shift(period).replace(0.0, np.nan) - 1.0)


def tsi(close, long: int = 25, short: int = 13) -> pd.Series:
    """True Strength Index, percent."""
    c = _as_series(close)
    m = c.diff()
    sm1 = ema(m.iloc[1:], long).reindex(c.index)
    sm2 = ema(sm1.dropna(), short).reindex(c.index)
    a1 = ema(m.iloc[1:].abs(), long).reindex(c.index)
    a2 = ema(a1.dropna(), short).reindex(c.index)
    return 100.0 * sm2 / a2.replace(0.0, np.nan)


def cmf(high, low, close, volume, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    h, l, c, v = (_as_series(x) for x in (high, low, close, volume))
    span = (h - l).replace(0.0, np.nan)
    mfm = ((c - l) - (h - c)) / span
    mfm = mfm.fillna(0.0)
    mfv = mfm * v
    vol_sum = v.rolling(period, min_periods=period).sum().replace(0.0, np.nan)
    return mfv.rolling(period, min_periods=period).sum() / vol_sum


def obv(close, volume) -> pd.Series:
    """On-Balance Volume (cumulative, starts at 0)."""
    c, v = _as_series(close), _as_series(volume)
    direction = np.sign(c.diff().fillna(0.0))
    return (direction * v).fillna(0.0).cumsum()


def mfi(high, low, close, volume, period: int = 14) -> pd.Series:
    """Money Flow Index — a simple (not Wilder) sum over the window, per the
    original Quong & Soudack definition."""
    h, l, c, v = (_as_series(x) for x in (high, low, close, volume))
    typical = (h + l + c) / 3.0
    raw_flow = typical * v
    delta = typical.diff()
    pos = raw_flow.where(delta > 0, 0.0)
    neg = raw_flow.where(delta < 0, 0.0)
    pos_sum = pos.rolling(period, min_periods=period).sum()
    neg_sum = neg.rolling(period, min_periods=period).sum()
    ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + ratio))
    return out.where(~((neg_sum == 0.0) & (pos_sum > 0.0)), 100.0)


def pvo(volume, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Percentage Volume Oscillator.  Columns: pvo, signal, hist."""
    v = _as_series(volume)
    fast_e, slow_e = ema(v, fast), ema(v, slow)
    line = 100.0 * (fast_e - slow_e) / slow_e.replace(0.0, np.nan)
    sig = ema(line.dropna(), signal).reindex(v.index)
    return pd.DataFrame({"pvo": line, "signal": sig, "hist": line - sig}, index=v.index)


def bollinger(close, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands.  Columns: mid, upper, lower, width, pct_b.

    ``width`` is normalised by the mid band (so it is comparable across
    symbols); ``pct_b`` is 0 at the lower band and 1 at the upper.
    """
    c = _as_series(close)
    mid = c.rolling(period, min_periods=period).mean()
    sd = c.rolling(period, min_periods=period).std(ddof=0)
    upper, lower = mid + num_std * sd, mid - num_std * sd
    span = (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {
            "mid": mid,
            "upper": upper,
            "lower": lower,
            "width": (upper - lower) / mid.replace(0.0, np.nan),
            "pct_b": (c - lower) / span,
        },
        index=c.index,
    )


def donchian(high, low, close, period: int = 20) -> pd.DataFrame:
    """Donchian channel.  Columns: upper, lower, mid, position (0..1)."""
    h, l, c = _as_series(high), _as_series(low), _as_series(close)
    upper = h.rolling(period, min_periods=period).max()
    lower = l.rolling(period, min_periods=period).min()
    span = (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {
            "upper": upper,
            "lower": lower,
            "mid": (upper + lower) / 2.0,
            "position": (c - lower) / span,
        },
        index=c.index,
    )


def zscore(values, period: int = 20) -> pd.Series:
    """Rolling z-score of the series against its own window."""
    s = _as_series(values)
    mean = s.rolling(period, min_periods=period).mean()
    sd = s.rolling(period, min_periods=period).std(ddof=0).replace(0.0, np.nan)
    return (s - mean) / sd


def trailing_return(close, period: int) -> pd.Series:
    """Simple trailing return over `period` bars, percent."""
    c = _as_series(close)
    return 100.0 * (c / c.shift(period).replace(0.0, np.nan) - 1.0)


def rolling_skew(close, period: int = 60) -> pd.Series:
    """Skewness of daily log returns over the window."""
    c = _as_series(close)
    rets = np.log(c / c.shift(1).replace(0.0, np.nan))
    return rets.rolling(period, min_periods=max(10, period // 2)).skew()


# ---------------------------------------------------------------------------
# Relative strength, beta and intraday structure.
#
# Everything above measures a stock in isolation. These measure it against the
# market, and against its own session — which is what the intraday playbook we
# were given is really asking for, translated to the timeframes this system
# can honestly support.
# ---------------------------------------------------------------------------
def align_pair(stock, benchmark):
    """Align two price series on their shared dates.

    Returns ``(stock, benchmark)`` restricted to timestamps present in both.
    A benchmark that stops early (a halted or delisted symbol) therefore
    shortens the window rather than producing silent NaNs.
    """
    a, b = _as_series(stock), _as_series(benchmark)
    shared = a.index.intersection(b.index)
    return a.reindex(shared).sort_index(), b.reindex(shared).sort_index()


def relative_strength(stock, benchmark, period: int = 20) -> pd.Series:
    """Stock return minus benchmark return over `period` bars, in percent.

    Positive means the stock outpaced the benchmark. This is the filter that
    stops us buying a name up 3% on a day the market is up 4%.
    """
    a, b = align_pair(stock, benchmark)
    if len(a) <= period:
        return pd.Series(dtype="float64", index=a.index)
    stock_ret = 100.0 * (a / a.shift(period).replace(0.0, np.nan) - 1.0)
    bench_ret = 100.0 * (b / b.shift(period).replace(0.0, np.nan) - 1.0)
    return stock_ret - bench_ret


def rolling_beta(stock, benchmark, period: int = 60) -> pd.Series:
    """Rolling CAPM beta of the stock against the benchmark.

    beta = cov(stock returns, benchmark returns) / var(benchmark returns)

    Used both for position sizing (a high-beta name gets a smaller
    allocation) and for Jensen's alpha in the performance analysis.
    """
    a, b = align_pair(stock, benchmark)
    stock_ret = a.pct_change()
    bench_ret = b.pct_change()
    min_obs = max(20, period // 3)
    cov = stock_ret.rolling(period, min_periods=min_obs).cov(bench_ret)
    var = bench_ret.rolling(period, min_periods=min_obs).var()

    # A benchmark with (near) zero variance makes beta explode: dividing by
    # 1e-20 of floating-point noise produced a beta of 6.5e10 in testing, which
    # would then drive position sizing to nonsense. Anything below this floor
    # is treated as "no usable benchmark variation" rather than as a number.
    var = var.where(var > 1e-12)
    beta = cov / var

    # Equity betas outside this range are a data problem, not a measurement.
    return beta.where(beta.abs() <= 5.0)


def opening_range(intraday: pd.DataFrame, bars: int = 1) -> dict:
    """High and low of the session's first `bars` intraday candles.

    With 15-minute bars, ``bars=1`` is the 09:30-09:45 opening range. Returns
    an empty dict when the frame does not cover a session open, so callers can
    treat "no range yet" differently from "range not broken".
    """
    if intraday is None or intraday.empty:
        return {}
    frame = intraday.sort_index()
    last_day = frame.index[-1].normalize()
    session = frame[frame.index.normalize() == last_day]
    if len(session) < bars:
        return {}
    window = session.iloc[:bars]
    high = float(window["high"].max())
    low = float(window["low"].min())
    last = float(session["close"].iloc[-1])
    span = high - low
    return {
        "high": high,
        "low": low,
        "last": last,
        # 0 at the range low, 1 at the range high, >1 is an upside breakout.
        "position": (last - low) / span if span > 0 else float("nan"),
        "bars_in_session": int(len(session)),
    }


def relative_volume(intraday: pd.DataFrame, lookback_sessions: int = 10) -> float:
    """Volume so far today against the same point in prior sessions.

    Above 1.0 means the stock is trading more heavily than usual for this time
    of day. NOTE: on Alpaca's free IEX feed this covers only a small slice of
    consolidated volume, so it is a weak confirming signal, never a gate.
    """
    if intraday is None or intraday.empty:
        return float("nan")
    frame = intraday.sort_index()
    days = sorted({ts.normalize() for ts in frame.index})
    if len(days) < 2:
        return float("nan")
    today = days[-1]
    session = frame[frame.index.normalize() == today]
    bars_so_far = len(session)
    if bars_so_far == 0:
        return float("nan")
    today_volume = float(session["volume"].sum())

    # Compare against the same number of bars from each earlier session, so a
    # 10:05 reading is not measured against a full prior day.
    history = []
    for day in days[-(lookback_sessions + 1) : -1]:
        prior = frame[frame.index.normalize() == day]
        if len(prior) >= bars_so_far:
            history.append(float(prior["volume"].iloc[:bars_so_far].sum()))
    if not history:
        return float("nan")
    baseline = float(np.mean(history))
    return today_volume / baseline if baseline > 0 else float("nan")
