#!/usr/bin/env python3
"""Rebuild the trade ledger for runs that happened before it existed.

The ledger (``trading-logs/trades_student_N.csv``) only started recording on
2026-10-25. Every trade before that is still on record at Alpaca, so this
script reads each member's order history and writes the missing rows back,
then computes an alpha row from the whole reconstructed history.

WHAT COMES BACK AND WHAT DOES NOT
---------------------------------
Alpaca knows symbol, side, quantity, average fill price and time. That is
everything the return, the excess return and Jensen's alpha need.

It does NOT know the composite score or the conviction that caused the order
-- those lived only in the run's ``model-run/`` artefact, which is gitignored
and expires after 30 days. So for backfilled trades the INFORMATION
COEFFICIENT CANNOT BE COMPUTED: there is no score to correlate the return
against. Backfilled rows are marked ``engine=backfilled_from_alpaca`` and
leave ``composite`` empty, which is exactly what a missing value should look
like -- it must never be guessed, because an invented score would corrupt the
one statistic the ledger exists to produce.

Beta is not recorded either, but unlike the score it can be MEASURED rather
than guessed: 60-day rolling beta against SPY, taken as of the entry date,
from the same price history the attribution already uses. That is the same
number the live path records, computed the same way.

Running it:

    python scripts/backfill_ledger.py                 # all students
    python scripts/backfill_ledger.py --students student_1
    python scripts/backfill_ledger.py --dry-run       # show, write nothing

Existing rows are never touched: an order already in the ledger is skipped by
its Alpaca order id, so the script is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system import alpha as alpha_lib  # noqa: E402
from trading_system import alpha_log, price_log, trade_ledger  # noqa: E402
from trading_system.alpaca_client import AlpacaError, build_client  # noqa: E402
from trading_system.config import load_config  # noqa: E402
from trading_system.indicators import rolling_beta  # noqa: E402

BACKFILL_ENGINE = "backfilled_from_alpaca"

IC_CAVEAT = (
    "backfilled from Alpaca order history: the composite score at entry was not "
    "recorded for these trades, so the information coefficient cannot be computed "
    "for them"
)


def eastern_hour(stamp: str) -> Optional[int]:
    """Rough ET hour of a UTC timestamp, for labelling morning vs afternoon."""
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    # -4 in summer, -5 in winter. One hour either way only matters at the
    # boundary between the two runs, which are five hours apart.
    offset = -4 if 3 < moment.month < 11 else -5
    return (moment.hour + offset) % 24


def run_label_for(stamp: str) -> str:
    hour = eastern_hour(stamp)
    if hour is None:
        return "backfilled"
    if hour < 12:
        return "morning"
    if hour < 15:
        return "midday"
    return "afternoon"


def fill_price(order: dict) -> float:
    for key in ("filled_avg_price", "limit_price", "stop_price"):
        value = order.get(key)
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            return price
    return float("nan")


def to_row(student_id: str, order: dict) -> Optional[Dict[str, str]]:
    """Turn one Alpaca order into a ledger row, or None if it never filled."""
    try:
        qty = float(order.get("filled_qty") or 0.0)
    except (TypeError, ValueError):
        qty = 0.0
    if qty <= 0:
        return None  # cancelled, rejected or still open: it did not happen

    price = fill_price(order)
    stamp = str(order.get("filled_at") or order.get("submitted_at") or "")
    date = stamp[:10]

    row = {key: "" for key in trade_ledger.COLUMNS}
    row.update(
        timestamp_utc=stamp,
        date=date,
        student_id=student_id,
        symbol=str(order.get("symbol", "")).upper(),
        side=str(order.get("side", "")).lower(),
        qty=f"{qty:.6f}",
        price="" if not math.isfinite(price) else f"{price:.6f}",
        notional="" if not math.isfinite(price) else f"{qty * price:.6f}",
        engine=BACKFILL_ENGINE,
        run_label=run_label_for(stamp),
        client_order_id=str(order.get("client_order_id", "")),
        alpaca_order_id=str(order.get("id", "")),
        status=str(order.get("status", "")),
        submitted="True",
    )
    return row


def measured_betas(bars, benchmark_bars, rows: List[Dict[str, str]]) -> Dict[str, float]:
    """60-day beta vs SPY as of each buy's entry date, per symbol+date."""
    out: Dict[str, float] = {}
    if benchmark_bars is None or len(benchmark_bars) == 0:
        return out
    for symbol, frame in (bars or {}).items():
        if frame is None or len(frame) < 30:
            continue
        series = rolling_beta(frame["close"], benchmark_bars["close"], period=60)
        for timestamp, value in series.items():
            if value is not None and math.isfinite(float(value)):
                out[f"{symbol}|{timestamp.strftime('%Y-%m-%d')}"] = float(value)
    return out


def nearest_beta(betas: Dict[str, float], symbol: str, date: str) -> float:
    """Beta on the entry date, or the latest one before it."""
    exact = betas.get(f"{symbol}|{date}")
    if exact is not None:
        return exact
    candidates = sorted(
        (k.split("|")[1] for k in betas if k.startswith(f"{symbol}|") and k.split("|")[1] <= date)
    )
    return betas[f"{symbol}|{candidates[-1]}"] if candidates else float("nan")


def backfill_student(cfg, student, dry_run: bool) -> dict:
    out = {"student": student.id, "name": student.name, "new_rows": 0, "error": ""}
    try:
        client = build_client(cfg, student, demo_override=False)
    except Exception as exc:
        out["error"] = f"could not build a client: {exc}"
        return out

    if not client.live:
        out["error"] = "no credentials for this member, so there is nothing to read"
        return out

    try:
        orders = client.get_order_history(status="all")
    except AlpacaError as exc:
        out["error"] = f"Alpaca refused the order history: {exc}"
        return out

    existing = trade_ledger.read_fills(student.id, cfg.log_dir)
    known = {r.get("alpaca_order_id", "") for r in existing if r.get("alpaca_order_id")}
    known |= {r.get("client_order_id", "") for r in existing if r.get("client_order_id")}

    fresh: List[Dict[str, str]] = []
    for order in orders:
        if str(order.get("id", "")) in known or str(order.get("client_order_id", "")) in known:
            continue
        row = to_row(student.id, order)
        if row:
            fresh.append(row)

    out["new_rows"] = len(fresh)
    out["already_logged"] = len(existing)

    combined = existing + fresh
    symbols = sorted({r["symbol"] for r in combined if r.get("symbol")})
    if not symbols:
        return out

    try:
        bars = client.get_bars(symbols + [alpha_lib.BENCHMARK], days=180)
    except AlpacaError as exc:
        bars = {}
        out["error"] = f"prices unavailable, beta left blank: {exc}"
    benchmark_bars = bars.get(alpha_lib.BENCHMARK)

    # Seed the committed price history whether or not there were new trades,
    # so re-running this is enough to give the dashboard its charts.
    if bars and not dry_run:
        seeded = price_log.append_closes(price_log.rows_from_bars(bars), cfg.log_dir)
        out["price_rows"] = seeded.get("rows", 0)

    if not fresh:
        return out

    betas = measured_betas(bars, benchmark_bars, fresh)
    for row in fresh:
        if row["side"] == "buy":
            beta = nearest_beta(betas, row["symbol"], row["date"])
            row["beta"] = "" if not math.isfinite(beta) else f"{beta:.6f}"

    if dry_run:
        out["preview"] = fresh[:8]
        return out

    status = trade_ledger.append_rows(fresh, cfg.log_dir)
    if not status.get("ok"):
        out["error"] = f"could not write the ledger: {status.get('error')}"
        return out

    # Now measure the whole reconstructed history.
    rows = trade_ledger.read_fills(student.id, cfg.log_dir)
    positions = alpha_lib.build_positions(rows)
    closes = {
        symbol: float(frame["close"].iloc[-1])
        for symbol, frame in bars.items()
        if frame is not None and len(frame)
    }
    alpha_lib.mark_open_positions(positions, closes)
    alpha_lib.attribute(positions, benchmark_bars)
    summary = alpha_lib.summarise(positions)

    alpha_status = alpha_log.append_row(
        alpha_log.build_row(
            student_id=student.id,
            summary=summary,
            run_label="backfill",
            data_source="ALPACA_LIVE",
            note=IC_CAVEAT,
        ),
        cfg.log_dir,
    )
    out["alpha"] = {
        "trades": summary.trades,
        "open": summary.open_trades,
        "mean_return_pct": summary.mean_return,
        "mean_excess_pct": summary.mean_excess,
        "mean_jensen_pct": summary.mean_jensen,
        "total_pnl": summary.total_pnl,
        "written": alpha_status.get("ok", False),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--students", default="all", help="all, or ids like student_1,student_3")
    parser.add_argument("--dry-run", action="store_true", help="print what would be written")
    args = parser.parse_args()

    cfg = load_config(args.config)
    wanted = args.students.strip().lower()
    if wanted in ("", "all", "*"):
        students = cfg.students
    else:
        ids = {s.strip().lower() for s in wanted.split(",") if s.strip()}
        students = [s for s in cfg.students if s.id.lower() in ids]
        unknown = ids - {s.id.lower() for s in cfg.students}
        if unknown:
            print(f"unknown student id(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2

    print(f"Alpaca endpoint : {cfg.alpaca_base_url}")
    print(f"Log directory   : {cfg.log_dir}")
    print(f"Mode            : {'DRY RUN (nothing written)' if args.dry_run else 'writing'}")
    print()

    failures = 0
    for student in students:
        result = backfill_student(cfg, student, args.dry_run)
        print(f"--- {student.id}  {student.name} ---")
        if result["error"]:
            print(f"  ! {result['error']}")
            failures += 1
        print(f"  already in the ledger : {result.get('already_logged', 0)}")
        print(f"  recovered from Alpaca : {result['new_rows']}")
        if result.get("price_rows"):
            print(f"  price history rows    : {result['price_rows']}")
        for row in result.get("preview", []):
            print(
                f"      {row['date']}  {row['side']:4s} {row['symbol']:6s} "
                f"qty={row['qty']:>10s} @ {row['price'] or 'n/a'}"
            )
        alpha = result.get("alpha")
        if alpha:
            print(
                f"  alpha now             : {alpha['trades']} trade(s), "
                f"{alpha['open']} open, mean excess "
                f"{alpha['mean_excess_pct']:+.2f}%, Jensen "
                f"{alpha['mean_jensen_pct']:+.2f}%, P&L ${alpha['total_pnl']:,.2f}"
            )
            print("  note                  : IC not computable for backfilled trades")
        print()

    if not args.dry_run:
        print("Commit the updated trading-logs/ files to publish them on GitHub.")
    return 1 if failures and failures == len(students) else 0


if __name__ == "__main__":
    raise SystemExit(main())
