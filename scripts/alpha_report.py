#!/usr/bin/env python3
"""Attribute performance to the trades that caused it.

Three questions, three measures:

  1. EXCESS RETURN   stock return - SPY return over the same window.
                     "Did we beat the market on the names we picked?"

  2. JENSEN'S ALPHA  stock return - beta x SPY return.
                     "Did we beat the market AFTER adjusting for the risk we
                     took?" This matters here: our book is deliberately
                     high-beta, so a stock up 3% while the market is up 4% is
                     underperformance dressed up as a gain.

  3. SIGNAL IC       correlation(composite score at entry, realised return).
                     "Do the 29 indicators predict anything at all?" Plus a
                     breakdown by conviction: if VERY_HIGH does not beat
                     MEDIUM, the conviction mechanism is decorative.

A caution printed in the output and worth repeating here: over a handful of
trading days every one of these numbers is dominated by noise. This is a
framework for judging the strategy, not yet a judgement of it.

    python scripts/alpha_report.py
    python scripts/alpha_report.py --demo        # synthetic prices, no keys
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system import indicators as ind  # noqa: E402
from trading_system.alpaca_client import (  # noqa: E402
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.config import load_config  # noqa: E402
from trading_system.trade_ledger import read_fills  # noqa: E402

BENCHMARK = "SPY"
#: Below this many closed/open trades, the summary statistics are reported
#: but explicitly flagged as not meaningful.
MEANINGFUL_SAMPLE = 30


def _f(value, default=float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def pct(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"{value:+.2f}%"


def money(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"${value:,.2f}"


class Position:
    """One buy, measured to its matching sell or to the latest close."""

    def __init__(self, row: Dict[str, str]):
        self.symbol = row["symbol"].upper()
        self.student_id = row["student_id"]
        self.entry_date = row["date"]
        self.entry_price = _f(row["price"])
        self.qty = _f(row["qty"])
        self.notional = _f(row["notional"])
        self.composite = _f(row["composite"])
        self.conviction = row.get("conviction", "")
        self.engine = row.get("engine", "")
        self.beta_at_entry = _f(row.get("beta"))
        self.exit_date: Optional[str] = None
        self.exit_price = float("nan")
        self.still_open = True

    def close_at(self, date: str, price: float) -> None:
        self.exit_date, self.exit_price, self.still_open = date, price, False

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


def build_positions(
    rows: List[Dict[str, str]], include_demo: bool = False
) -> List[Position]:
    """Pair buys with later sells of the same symbol, FIFO.

    Orders that never reached the market are skipped: an order withheld for
    approval, rejected, or simulated in demo mode did not happen and must not
    appear in a performance report. ``include_demo`` relaxes that for
    previewing the report's shape before real trades accumulate, and the
    output says so.
    """
    open_by_symbol: Dict[str, List[Position]] = defaultdict(list)
    positions: List[Position] = []
    for row in sorted(rows, key=lambda r: r.get("timestamp_utc", "")):
        submitted = str(row.get("submitted", "")).lower() in ("true", "1")
        demo = str(row.get("status", "")).lower() == "accepted_demo"
        if not submitted and not (include_demo and demo):
            continue  # withheld, rejected or simulated orders never existed
        side = row.get("side", "").lower()
        symbol = row.get("symbol", "").upper()
        if side == "buy":
            position = Position(row)
            positions.append(position)
            open_by_symbol[symbol].append(position)
        elif side == "sell":
            price, date = _f(row.get("price")), row.get("date", "")
            while open_by_symbol[symbol]:
                open_by_symbol[symbol].pop(0).close_at(date, price)
    return positions


def mark_open_positions(positions: List[Position], closes: Dict[str, float]) -> None:
    for position in positions:
        if position.still_open:
            price = closes.get(position.symbol, float("nan"))
            if math.isfinite(price):
                position.exit_price = price


def benchmark_return(bars, start_date: str, end_date: Optional[str]) -> float:
    """SPY return over the same window as a trade, in percent."""
    if bars is None or bars.empty:
        return float("nan")
    frame = bars.sort_index()
    dates = [ts.strftime("%Y-%m-%d") for ts in frame.index]
    try:
        i = next(n for n, d in enumerate(dates) if d >= start_date)
    except StopIteration:
        return float("nan")
    if end_date:
        matching = [n for n, d in enumerate(dates) if d <= end_date]
        j = matching[-1] if matching else len(dates) - 1
    else:
        j = len(dates) - 1
    if j <= i:
        return 0.0
    a = float(frame["close"].iloc[i])
    b = float(frame["close"].iloc[j])
    return 100.0 * (b / a - 1.0) if a > 0 else float("nan")


def correlation(xs: List[float], ys: List[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    xs2 = [p[0] for p in pairs]
    ys2 = [p[1] for p in pairs]
    if len(set(xs2)) < 2 or len(set(ys2)) < 2:
        return float("nan")
    try:
        return statistics.correlation(xs2, ys2)
    except statistics.StatisticsError:
        return float("nan")


def mean(values: List[float]) -> float:
    clean = [v for v in values if math.isfinite(v)]
    return statistics.fmean(clean) if clean else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-trade alpha attribution")
    parser.add_argument("--config", default=None)
    parser.add_argument("--demo", action="store_true", help="synthetic prices, no keys")
    parser.add_argument(
        "--include-demo",
        action="store_true",
        help="also count simulated demo orders, to preview the report's shape",
    )
    parser.add_argument("--out", default="analysis/alpha_report.md")
    args = parser.parse_args()

    if args.demo:
        os.environ["DEMO_MODE"] = "true"
    cfg = load_config(args.config)

    everything: Dict[str, List[Position]] = {}
    symbols: set = set()
    for student in cfg.students:
        rows = read_fills(student.id, cfg.log_dir)
        positions = build_positions(rows, include_demo=args.include_demo)
        everything[student.id] = positions
        symbols.update(p.symbol for p in positions)

    if not symbols:
        print("No trades recorded yet — the ledger holds no submitted orders.")
        print(f"It fills as orders are submitted; see {cfg.log_dir}/trades_*.csv")
        print("(Pass --include-demo to preview the report using simulated orders.)")
        return 0

    # One batched request covers every traded symbol plus the benchmark.
    client = build_client(cfg, cfg.students[0], demo_override=True if args.demo else None)
    try:
        bars = client.get_bars(sorted(symbols | {BENCHMARK}), days=120)
    except (MarketDataUnavailable, AlpacaError) as exc:
        print(f"Cannot price the trades: {exc}")
        return 1

    closes = {
        sym: float(frame["close"].iloc[-1])
        for sym, frame in bars.items()
        if not frame.empty
    }
    spy = bars.get(BENCHMARK)

    lines: List[str] = [
        "# Alpha attribution",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"from `{cfg.log_dir}/trades_*.csv`.",
        "",
        *(
            ["> **PREVIEW ONLY.** This report counts simulated demo orders that "
             "never reached the market. The numbers below are not real "
             "performance.", ""]
            if args.include_demo
            else []
        ),
        "Three measures, answering three different questions:",
        "",
        "- **Excess return** — stock return minus SPY over the same window. "
        "Did we beat the market on the names we picked?",
        "- **Jensen's alpha** — stock return minus beta x SPY return. Did we beat "
        "the market *after adjusting for the risk taken*? Our book is "
        "deliberately high-beta, so this is the stricter and more honest test.",
        "- **Signal IC** — correlation between the composite score at entry and "
        "the realised return. Do the indicators predict anything?",
        "",
    ]

    all_positions: List[Position] = []
    for student in cfg.students:
        positions = everything[student.id]
        lines += [f"## {student.name} ({student.roll_no})", ""]
        if not positions:
            lines += ["_No trades recorded._", ""]
            continue

        mark_open_positions(positions, closes)
        rows_md = []
        for p in positions:
            bench = benchmark_return(spy, p.entry_date, p.exit_date)
            stock = p.stock_return
            excess = stock - bench if math.isfinite(stock) and math.isfinite(bench) else float("nan")
            beta = p.beta_at_entry if math.isfinite(p.beta_at_entry) else 1.0
            jensen = (
                stock - beta * bench
                if math.isfinite(stock) and math.isfinite(bench)
                else float("nan")
            )
            p.excess, p.jensen, p.bench = excess, jensen, bench  # type: ignore[attr-defined]
            rows_md.append(
                f"| {p.symbol} | {p.entry_date} | {p.exit_date or 'open'} | "
                f"{money(p.entry_price)} | {money(p.exit_price)} | {pct(stock)} | "
                f"{pct(bench)} | {pct(excess)} | {beta:.2f} | {pct(jensen)} | "
                f"{p.conviction} | {money(p.pnl)} |"
            )
        all_positions.extend(positions)

        lines += [
            "| Symbol | Entry | Exit | Entry px | Mark px | Return | SPY | Excess | Beta | Jensen | Conviction | P&L |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            *rows_md,
            "",
            f"- Trades: **{len(positions)}** "
            f"({sum(1 for p in positions if p.still_open)} still open)",
            f"- Mean excess return: **{pct(mean([p.excess for p in positions]))}**",
            f"- Mean Jensen's alpha: **{pct(mean([p.jensen for p in positions]))}**",
            f"- Total P&L on these trades: **{money(sum(p.pnl for p in positions if math.isfinite(p.pnl)))}**",
            "",
        ]

    # ---- group-level signal quality ----
    lines += ["## Does the signal predict anything?", ""]
    composites = [p.composite for p in all_positions]
    returns = [p.stock_return for p in all_positions]
    excesses = [p.excess for p in all_positions]  # type: ignore[attr-defined]

    ic_raw = correlation(composites, returns)
    ic_excess = correlation(composites, excesses)
    lines += [
        "| Measure | Value | Reading |",
        "| --- | --- | --- |",
        f"| IC (score vs raw return) | {ic_raw:+.3f} |"
        f" {'positive — scores ranked outcomes correctly' if ic_raw > 0.05 else 'no usable relationship yet'} |",
        f"| IC (score vs excess return) | {ic_excess:+.3f} |"
        f" {'positive' if ic_excess > 0.05 else 'no usable relationship yet'} |",
        f"| Trades in sample | {len(all_positions)} |"
        f" {'adequate' if len(all_positions) >= MEANINGFUL_SAMPLE else 'TOO SMALL to be meaningful'} |",
        "",
        "### By conviction",
        "",
        "If the ensemble works, higher conviction should earn more. If these "
        "rows are indistinguishable, the conviction mechanism is decorative.",
        "",
        "| Conviction | Trades | Mean return | Mean excess | Mean Jensen |",
        "| --- | --- | --- | --- | --- |",
    ]
    for level in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW"):
        bucket = [p for p in all_positions if p.conviction == level]
        if not bucket:
            continue
        lines.append(
            f"| {level} | {len(bucket)} | "
            f"{pct(mean([p.stock_return for p in bucket]))} | "
            f"{pct(mean([p.excess for p in bucket]))} | "  # type: ignore[attr-defined]
            f"{pct(mean([p.jensen for p in bucket]))} |"  # type: ignore[attr-defined]
        )

    lines += [
        "",
        "### By engine",
        "",
        "| Engine | Trades | Mean excess return |",
        "| --- | --- | --- |",
    ]
    for engine in sorted({p.engine for p in all_positions if p.engine}):
        bucket = [p for p in all_positions if p.engine == engine]
        lines.append(
            f"| {engine} | {len(bucket)} | "
            f"{pct(mean([p.excess for p in bucket]))} |"  # type: ignore[attr-defined]
        )

    lines += [
        "",
        "---",
        "",
        "## How to read this",
        "",
        f"There are **{len(all_positions)} trades** in this sample. Statistical "
        f"significance needs far more — {MEANINGFUL_SAMPLE}+ as a bare minimum, "
        "and realistically hundreds. Beta is estimated from 60 days of returns "
        "and is itself noisy over a short period.",
        "",
        "Every number above is therefore **descriptive, not evidence**. They "
        "describe what happened; they do not establish that the strategy works "
        "or that it does not. Treat this as the measurement framework, and "
        "judge the strategy only once the sample is large enough to carry the "
        "weight.",
        "",
        f"Data source for marks: `{client.data_source}`.",
        "",
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote {out_path} — {len(all_positions)} trade(s) across "
          f"{len(everything)} member(s)")
    print(f"  mean excess return : {pct(mean(excesses))}")
    print(f"  mean Jensen alpha  : {pct(mean([p.jensen for p in all_positions]))}")
    print(f"  signal IC          : {ic_raw:+.3f}")
    if len(all_positions) < MEANINGFUL_SAMPLE:
        print(f"  NOTE: {len(all_positions)} trades is too small to be meaningful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
