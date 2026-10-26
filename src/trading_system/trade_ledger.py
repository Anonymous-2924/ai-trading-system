"""Per-trade records, so performance can be attributed rather than guessed.

The daily log answers "where is the account today". It cannot answer "was
NVDA a good trade", "did VERY_HIGH conviction beat MEDIUM", or "did we beat
the market on the names we picked", because it only stores daily totals.

This ledger stores one row per order we send, carrying the signal that caused
it — the composite score, the conviction, which engine decided, and the
volatility scale used to size it. ``scripts/alpha_report.py`` joins these
rows against later prices to produce excess return, Jensen's alpha and the
information coefficient.

Like the daily log, a failure here never breaks a trading run.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

#: Append-only. Never reorder, or existing history stops lining up.
COLUMNS: List[str] = [
    "timestamp_utc",
    "date",
    "student_id",
    "symbol",
    "side",
    "qty",
    "price",
    "notional",
    "composite",
    "conviction",
    "engine",
    "run_label",
    "volatility_scale",
    "natr_pct",
    "beta",
    "stop_loss",
    "take_profit",
    "bracket",
    "sector",
    "high_beta",
    "client_order_id",
    "alpaca_order_id",
    "status",
    "submitted",
]


def _num(value) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if not math.isfinite(f) else f"{f:.6f}"


@dataclass
class Fill:
    """One order we sent, with the signal that caused it."""

    timestamp_utc: str = ""
    date: str = ""
    student_id: str = ""
    symbol: str = ""
    side: str = ""
    qty: float = float("nan")
    price: float = float("nan")
    notional: float = float("nan")
    composite: float = float("nan")
    conviction: str = ""
    engine: str = ""
    run_label: str = ""
    volatility_scale: float = float("nan")
    natr_pct: float = float("nan")
    beta: float = float("nan")
    stop_loss: float = float("nan")
    take_profit: float = float("nan")
    bracket: bool = False
    sector: str = ""
    high_beta: bool = False
    client_order_id: str = ""
    alpaca_order_id: str = ""
    status: str = ""
    submitted: bool = False

    def as_csv_dict(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key in COLUMNS:
            value = getattr(self, key, "")
            if isinstance(value, float):
                out[key] = _num(value)
            elif isinstance(value, bool):
                out[key] = "true" if value else "false"
            else:
                out[key] = str(value).replace("\n", " ").replace("\r", " ")
        return out


def build_fill(
    *,
    student_id: str,
    order,
    result: Optional[Dict] = None,
    engine: str = "",
    run_label: str = "",
    when: Optional[datetime] = None,
) -> Fill:
    """Combine a planned order with whatever Alpaca said about it."""
    when = when or datetime.now(timezone.utc)
    result = result or {}
    filled_price = result.get("filled_avg_price")
    try:
        price = float(filled_price) if filled_price else float(order.price)
    except (TypeError, ValueError):
        price = float(order.price)

    return Fill(
        timestamp_utc=when.isoformat(timespec="seconds"),
        date=when.strftime("%Y-%m-%d"),
        student_id=student_id,
        symbol=order.symbol,
        side=order.side,
        qty=float(order.qty),
        price=price,
        notional=float(order.notional),
        composite=float(order.composite),
        conviction=order.conviction,
        engine=engine,
        run_label=run_label,
        volatility_scale=float(getattr(order, "volatility_scale", float("nan"))),
        natr_pct=float(getattr(order, "natr_pct", float("nan"))),
        beta=float(getattr(order, "beta", float("nan"))),
        stop_loss=float(order.stop_loss) if order.stop_loss else float("nan"),
        take_profit=float(order.take_profit) if order.take_profit else float("nan"),
        bracket=bool(result.get("bracket", False)),
        sector=order.sector,
        high_beta=bool(order.high_beta),
        client_order_id=order.client_order_id,
        alpaca_order_id=str(result.get("id") or ""),
        status=str(result.get("status") or ""),
        submitted=bool(result.get("submitted", False)),
    )


def append_fills(fills, log_dir: str = "trading-logs") -> Dict[str, object]:
    """Append rows to ``<log_dir>/trades_<student>.csv``.  Never raises."""
    status: Dict[str, object] = {"ok": False, "written": 0, "paths": [], "error": ""}
    try:
        rows = list(fills)
        if not rows:
            status["ok"] = True
            return status
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)

        by_student: Dict[str, List[Fill]] = {}
        for fill in rows:
            by_student.setdefault(fill.student_id, []).append(fill)

        for student_id, student_rows in by_student.items():
            path = directory / f"trades_{student_id}.csv"
            is_new = not path.exists() or path.stat().st_size == 0
            with path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS)
                if is_new:
                    writer.writeheader()
                for fill in student_rows:
                    writer.writerow(fill.as_csv_dict())
            status["paths"].append(path.as_posix())
            status["written"] = int(status["written"]) + len(student_rows)
        status["ok"] = True
    except Exception as exc:  # a ledger failure must not break a trading run
        log.exception("failed to append trade ledger rows")
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


def read_fills(student_id: str, log_dir: str = "trading-logs") -> List[Dict[str, str]]:
    path = Path(log_dir) / f"trades_{student_id}.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    except Exception:
        log.exception("failed to read %s", path)
        return []
