"""Closing prices, committed to the repository alongside the logs.

The dashboard needs price history to draw a stock's trajectory. Fetching it
live means Alpaca credentials, which makes a read-only results page ask for
keys it has no business needing -- and gives a blank chart to anyone who
declines.

So every run records the closes it already fetched. They land in
``trading-logs/prices.csv`` and are committed like every other log, which
means the dashboard can draw the whole history from the repository with no
credentials at all.

One row per symbol per day. Re-recording a day you already have is harmless:
the row is identical, and ``append_closes`` drops duplicates before writing.

As with every other log here, a failure never breaks a trading run.
"""

from __future__ import annotations

import csv
import logging
import math
from pathlib import Path
from typing import Dict, List, Sequence

log = logging.getLogger(__name__)

FILENAME = "prices.csv"

COLUMNS: List[str] = ["date", "symbol", "close"]

#: Enough to show a trajectory without the file growing without bound.
#: ~45 symbols x 180 days is well under a megabyte.
MAX_DAYS = 180


def read_closes(log_dir: str = "trading-logs") -> List[Dict[str, str]]:
    path = Path(log_dir) / FILENAME
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    except Exception:
        log.exception("failed to read %s", path)
        return []


def rows_from_bars(bars, symbols: Sequence[str] = ()) -> List[Dict[str, str]]:
    """Flatten ``{symbol: DataFrame}`` into date/symbol/close rows."""
    wanted = {str(s).upper() for s in symbols} if symbols else None
    out: List[Dict[str, str]] = []
    for symbol, frame in (bars or {}).items():
        symbol = str(symbol).upper()
        if wanted is not None and symbol not in wanted:
            continue
        if frame is None or len(frame) == 0 or "close" not in frame:
            continue
        tail = frame.sort_index().tail(MAX_DAYS)
        for timestamp, close in tail["close"].items():
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            try:
                date = timestamp.strftime("%Y-%m-%d")
            except AttributeError:
                date = str(timestamp)[:10]
            out.append({"date": date, "symbol": symbol, "close": f"{value:.6f}"})
    return out


def append_closes(rows, log_dir: str = "trading-logs") -> Dict[str, object]:
    """Merge rows into ``prices.csv``, keeping one row per symbol per day.

    The whole file is rewritten rather than appended to, because a later run
    on the same day carries a better close than an earlier one -- the last
    value for a (date, symbol) wins.  Never raises.
    """
    status: Dict[str, object] = {"ok": False, "rows": 0, "path": "", "error": ""}
    try:
        rows = list(rows)
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / FILENAME

        merged: Dict[str, Dict[str, str]] = {}
        for row in read_closes(log_dir) + rows:
            date = str(row.get("date", ""))
            symbol = str(row.get("symbol", "")).upper()
            close = str(row.get("close", ""))
            if not (date and symbol and close):
                continue
            merged[f"{date}|{symbol}"] = {"date": date, "symbol": symbol, "close": close}

        if not merged:
            status["ok"] = True
            return status

        keep = sorted({r["date"] for r in merged.values()})[-MAX_DAYS:]
        kept = {k: v for k, v in merged.items() if v["date"] in set(keep)}

        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            for key in sorted(kept, key=lambda k: (kept[k]["date"], kept[k]["symbol"])):
                writer.writerow(kept[key])

        status.update(ok=True, rows=len(kept), path=path.as_posix())
    except Exception as exc:  # logging must never break a trading run
        log.exception("failed to write the price history")
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


def to_frames(log_dir: str = "trading-logs"):
    """``{symbol: DataFrame}`` with a date index, the shape the charts expect."""
    import pandas as pd

    rows = read_closes(log_dir)
    if not rows:
        return {}
    frame = pd.DataFrame(rows)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["close", "date"])
    out = {}
    for symbol, group in frame.groupby("symbol"):
        group = group.sort_values("date").set_index("date")
        out[str(symbol)] = group[["close"]]
    return out
