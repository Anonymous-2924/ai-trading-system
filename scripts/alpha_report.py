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

from trading_system.alpaca_client import (  # noqa: E402
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.alpha import (  # noqa: E402
    BENCHMARK,
    MEANINGFUL_SAMPLE,
    attribute,
    build_positions,
    mark_open_positions,
    mean,
    summarise,
)
from trading_system.config import load_config  # noqa: E402
from trading_system.trade_ledger import read_fills  # noqa: E402


def pct(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"{value:+.2f}%"


def money(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"${value:,.2f}"


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
    for positions in everything.values():
        mark_open_positions(positions, closes)
        attribute(positions, spy)

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

        rows_md = []
        for p in positions:
            beta = p.beta_at_entry if math.isfinite(p.beta_at_entry) else 1.0
            rows_md.append(
                f"| {p.symbol} | {p.entry_date} | {p.exit_date or 'open'} | "
                f"{money(p.entry_price)} | {money(p.exit_price)} | "
                f"{pct(p.stock_return)} | {pct(p.benchmark_return)} | "
                f"{pct(p.excess)} | {beta:.2f} | {pct(p.jensen)} | "
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
    overall = summarise(all_positions)
    ic_raw, ic_excess = overall.ic_return, overall.ic_excess
    excesses = [p.excess for p in all_positions]
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
    for level, stats in overall.by_conviction.items():
        lines.append(
            f"| {level} | {stats['trades']} | {pct(stats['mean_return'])} | "
            f"{pct(stats['mean_excess'])} | {pct(stats['mean_jensen'])} |"
        )

    lines += [
        "",
        "### By engine",
        "",
        "| Engine | Trades | Mean excess return |",
        "| --- | --- | --- |",
    ]
    for engine, stats in overall.by_engine.items():
        lines.append(f"| {engine} | {stats['trades']} | {pct(stats['mean_excess'])} |")

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
    print(f"  mean Jensen alpha  : {pct(overall.mean_jensen)}")
    print(f"  signal IC          : {ic_raw:+.3f}")
    if len(all_positions) < MEANINGFUL_SAMPLE:
        print(f"  NOTE: {len(all_positions)} trades is too small to be meaningful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
