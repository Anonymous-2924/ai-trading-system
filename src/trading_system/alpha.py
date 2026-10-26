"""Performance attribution: did the trades we made actually earn anything?

Shared by ``scripts/alpha_report.py`` (which renders Markdown for the repo)
and the dashboard (which renders widgets), so both can never disagree.

Three measures, three questions:

  EXCESS RETURN   stock return - benchmark return over the same window.
                  "Did we beat the market on the names we picked?"

  JENSEN'S ALPHA  stock return - beta x benchmark return.
                  "Did we beat it AFTER adjusting for the risk we took?"
                  The honest test for a deliberately high-beta book: a stock
                  up 3% while the market is up 4% has underperformed what its
                  risk should have paid.

  INFORMATION     correlation(composite score at entry, realised return).
  COEFFICIENT     "Do the 29 indicators predict anything at all?"

Over a handful of trading days all of these are dominated by noise. They are
a framework for judging the strategy, not yet a judgement of it.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

BENCHMARK = "SPY"

#: Below this many trades the statistics are reported but flagged as not
#: meaningful. Even this is generous — real significance needs hundreds.
MEANINGFUL_SAMPLE = 30


def as_float(value, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def mean(values: Sequence[float]) -> float:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(clean) if clean else float("nan")


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    pairs = [
        (x, y)
        for x, y in zip(xs, ys)
        if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
    ]
    if len(pairs) < 3:
        return float("nan")
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]
    if len(set(a)) < 2 or len(set(b)) < 2:
        return float("nan")
    try:
        return statistics.correlation(a, b)
    except statistics.StatisticsError:
        return float("nan")


@dataclass
class Position:
    """One buy, measured to its matching sell or to the latest mark."""

    symbol: str = ""
    student_id: str = ""
    entry_date: str = ""
    entry_price: float = float("nan")
    qty: float = float("nan")
    notional: float = float("nan")
    composite: float = float("nan")
    conviction: str = ""
    engine: str = ""
    run_label: str = ""
    beta_at_entry: float = float("nan")
    exit_date: Optional[str] = None
    exit_price: float = float("nan")
    still_open: bool = True
    # filled in by attribute()
    benchmark_return: float = float("nan")
    excess: float = float("nan")
    jensen: float = float("nan")

    @property
    def stock_return(self) -> float:
        if not (math.isfinite(self.entry_price) and self.entry_price > 0):
            return float("nan")
        if not math.isfinite(self.exit_price):
            return float("nan")
        return 100.0 * (self.exit_price / self.entry_price - 1.0)

    @property
    def pnl(self) -> float:
        r = self.stock_return
        return float("nan") if not math.isfinite(r) else self.notional * r / 100.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date,
            "exit_date": self.exit_date or "open",
            "entry_price": self.entry_price,
            "mark_price": self.exit_price,
            "return_pct": self.stock_return,
            "benchmark_pct": self.benchmark_return,
            "excess_pct": self.excess,
            "beta": self.beta_at_entry,
            "jensen_pct": self.jensen,
            "conviction": self.conviction,
            "engine": self.engine,
            "pnl": self.pnl,
            "notional": self.notional,
            "still_open": self.still_open,
        }


def build_positions(
    rows: Sequence[Dict[str, str]], include_demo: bool = False
) -> List[Position]:
    """Pair each buy with a later sell of the same symbol, FIFO.

    Orders that never reached the market are skipped: one withheld for
    approval, rejected, or simulated in demo mode did not happen and must not
    appear in a performance report. ``include_demo`` relaxes that so the
    report's shape can be previewed before real trades accumulate.
    """
    open_by_symbol: Dict[str, List[Position]] = defaultdict(list)
    positions: List[Position] = []

    for row in sorted(rows, key=lambda r: r.get("timestamp_utc", "")):
        submitted = str(row.get("submitted", "")).lower() in ("true", "1")
        demo = str(row.get("status", "")).lower() == "accepted_demo"
        if not submitted and not (include_demo and demo):
            continue

        symbol = str(row.get("symbol", "")).upper()
        side = str(row.get("side", "")).lower()

        if side == "buy":
            position = Position(
                symbol=symbol,
                student_id=row.get("student_id", ""),
                entry_date=row.get("date", ""),
                entry_price=as_float(row.get("price")),
                qty=as_float(row.get("qty")),
                notional=as_float(row.get("notional")),
                composite=as_float(row.get("composite")),
                conviction=row.get("conviction", ""),
                engine=row.get("engine", ""),
                run_label=row.get("run_label", ""),
                beta_at_entry=as_float(row.get("beta")),
            )
            positions.append(position)
            open_by_symbol[symbol].append(position)
        elif side == "sell":
            price = as_float(row.get("price"))
            date = row.get("date", "")
            while open_by_symbol[symbol]:
                closing = open_by_symbol[symbol].pop(0)
                closing.exit_date, closing.exit_price = date, price
                closing.still_open = False
    return positions


def mark_open_positions(positions: Sequence[Position], closes: Dict[str, float]) -> None:
    """Value still-open positions at the latest available close."""
    for position in positions:
        if position.still_open:
            price = closes.get(position.symbol, float("nan"))
            if math.isfinite(price):
                position.exit_price = price


def benchmark_return(bars, start_date: str, end_date: Optional[str]) -> float:
    """Benchmark return over the same window as a trade, in percent."""
    if bars is None or len(bars) == 0:
        return float("nan")
    frame = bars.sort_index()
    dates = [ts.strftime("%Y-%m-%d") for ts in frame.index]
    try:
        i = next(n for n, d in enumerate(dates) if d >= start_date)
    except StopIteration:
        return float("nan")
    if end_date:
        earlier = [n for n, d in enumerate(dates) if d <= end_date]
        j = earlier[-1] if earlier else len(dates) - 1
    else:
        j = len(dates) - 1
    if j <= i:
        return 0.0
    a = float(frame["close"].iloc[i])
    b = float(frame["close"].iloc[j])
    return 100.0 * (b / a - 1.0) if a > 0 else float("nan")


def attribute(positions: Sequence[Position], benchmark_bars) -> None:
    """Fill in benchmark return, excess and Jensen's alpha for each position."""
    for p in positions:
        bench = benchmark_return(benchmark_bars, p.entry_date, p.exit_date)
        stock = p.stock_return
        p.benchmark_return = bench
        if math.isfinite(stock) and math.isfinite(bench):
            beta = p.beta_at_entry if math.isfinite(p.beta_at_entry) else 1.0
            p.excess = stock - bench
            p.jensen = stock - beta * bench
        else:
            p.excess = float("nan")
            p.jensen = float("nan")


@dataclass
class Summary:
    """Headline numbers for a set of positions."""

    trades: int = 0
    open_trades: int = 0
    mean_excess: float = float("nan")
    mean_jensen: float = float("nan")
    mean_return: float = float("nan")
    total_pnl: float = float("nan")
    win_rate: float = float("nan")
    ic_return: float = float("nan")
    ic_excess: float = float("nan")
    by_conviction: Dict[str, dict] = field(default_factory=dict)
    by_engine: Dict[str, dict] = field(default_factory=dict)

    @property
    def meaningful(self) -> bool:
        return self.trades >= MEANINGFUL_SAMPLE


def summarise(positions: Sequence[Position]) -> Summary:
    """Collapse positions into the headline measures."""
    positions = list(positions)
    if not positions:
        return Summary()

    returns = [p.stock_return for p in positions]
    wins = [r for r in returns if math.isfinite(r)]

    summary = Summary(
        trades=len(positions),
        open_trades=sum(1 for p in positions if p.still_open),
        mean_excess=mean([p.excess for p in positions]),
        mean_jensen=mean([p.jensen for p in positions]),
        mean_return=mean(returns),
        total_pnl=sum(p.pnl for p in positions if math.isfinite(p.pnl)),
        win_rate=(100.0 * sum(1 for r in wins if r > 0) / len(wins)) if wins else float("nan"),
        ic_return=correlation([p.composite for p in positions], returns),
        ic_excess=correlation([p.composite for p in positions], [p.excess for p in positions]),
    )

    for level in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW"):
        bucket = [p for p in positions if p.conviction == level]
        if bucket:
            summary.by_conviction[level] = {
                "trades": len(bucket),
                "mean_return": mean([p.stock_return for p in bucket]),
                "mean_excess": mean([p.excess for p in bucket]),
                "mean_jensen": mean([p.jensen for p in bucket]),
            }

    for engine in sorted({p.engine for p in positions if p.engine}):
        bucket = [p for p in positions if p.engine == engine]
        summary.by_engine[engine] = {
            "trades": len(bucket),
            "mean_excess": mean([p.excess for p in bucket]),
        }
    return summary
