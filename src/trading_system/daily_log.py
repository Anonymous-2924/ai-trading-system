"""Per-member daily logs: ``trading-logs/student_N.csv`` + ``student_N.md``.

These files are COMMITTED to git deliberately.  The GitHub Actions workflow
pushes them back after every run, so a 15-20 day history accumulates in the
repository rather than evaporating with the runner.

Two rules the brief is explicit about and that are enforced here:

* **A run that cannot read the account still appends a row.**  The row carries
  ``data_source=UNAVAILABLE`` and whatever is known, so a gap in the record is
  visible as a row rather than as a missing day.
* **A logging failure never breaks a trading run.**  Every public function
  catches its own exceptions and returns a status instead of raising.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

#: Column order of the CSV.  Append-only — never reorder, or existing history
#: stops lining up.
COLUMNS: List[str] = [
    "timestamp_utc",
    "date",
    "student_id",
    "equity",
    "cash",
    "buying_power",
    "day_pl",
    "day_pl_pct",
    "total_pl",
    "total_pl_pct",
    "open_positions",
    "buy_signals",
    "sell_signals",
    "hold_signals",
    "orders_submitted",
    "data_source",
    "engine",
    "mode",
    "notes",
]


@dataclass
class DailyRow:
    timestamp_utc: str = ""
    date: str = ""
    student_id: str = ""
    equity: float = float("nan")
    cash: float = float("nan")
    buying_power: float = float("nan")
    day_pl: float = float("nan")
    day_pl_pct: float = float("nan")
    total_pl: float = float("nan")
    total_pl_pct: float = float("nan")
    open_positions: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    hold_signals: int = 0
    orders_submitted: int = 0
    data_source: str = "UNAVAILABLE"
    engine: str = ""
    mode: str = ""
    notes: str = ""

    def as_csv_dict(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key in COLUMNS:
            value = getattr(self, key, "")
            if isinstance(value, float):
                out[key] = "" if not math.isfinite(value) else f"{value:.4f}"
            else:
                out[key] = str(value).replace("\n", " ").replace("\r", " ")
        return out


def build_row(
    *,
    student_id: str,
    starting_equity: float,
    account: Optional[Dict] = None,
    counts: Optional[Dict[str, int]] = None,
    open_positions: int = 0,
    orders_submitted: int = 0,
    data_source: str = "UNAVAILABLE",
    engine: str = "",
    mode: str = "",
    notes: str = "",
    when: Optional[datetime] = None,
) -> DailyRow:
    """Assemble one row.

    ``account`` may be ``None`` — that is the "could not read the account"
    case, and the row is still produced so the gap is visible.
    """
    when = when or datetime.now(timezone.utc)
    counts = counts or {}
    row = DailyRow(
        timestamp_utc=when.isoformat(timespec="seconds"),
        date=when.strftime("%Y-%m-%d"),
        student_id=student_id,
        open_positions=int(open_positions),
        buy_signals=int(counts.get("BUY", 0)),
        sell_signals=int(counts.get("SELL", 0)),
        hold_signals=int(counts.get("HOLD", 0)),
        orders_submitted=int(orders_submitted),
        data_source=data_source,
        engine=engine,
        mode=mode,
        notes=notes,
    )
    if account:
        equity = _num(account.get("equity"))
        last_equity = _num(account.get("last_equity"))
        row.equity = equity
        row.cash = _num(account.get("cash"))
        row.buying_power = _num(account.get("buying_power"))
        if math.isfinite(equity) and math.isfinite(last_equity) and last_equity:
            # DAY P&L is the move since the PREVIOUS CLOSE, which is what
            # Alpaca's last_equity holds.
            row.day_pl = equity - last_equity
            row.day_pl_pct = (equity / last_equity - 1.0) * 100.0
        if math.isfinite(equity) and starting_equity:
            row.total_pl = equity - starting_equity
            row.total_pl_pct = (equity / starting_equity - 1.0) * 100.0
    else:
        row.notes = (
            (notes + " | " if notes else "")
            + "account unreadable on this run; row appended so the gap is visible"
        )
    return row


def _num(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def append_row(row: DailyRow, log_dir: str = "trading-logs") -> Dict[str, object]:
    """Append to the CSV and rebuild the Markdown mirror.  Never raises."""
    status: Dict[str, object] = {"ok": False, "csv": "", "md": "", "error": ""}
    try:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        csv_path = directory / f"{row.student_id}.csv"
        is_new = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row.as_csv_dict())
        status["csv"] = csv_path.as_posix()
        status["md"] = write_markdown(row.student_id, log_dir) or ""
        status["ok"] = True
    except Exception as exc:  # logging must never break a trading run
        log.exception("failed to append daily log row")
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


def read_rows(student_id: str, log_dir: str = "trading-logs") -> List[Dict[str, str]]:
    path = Path(log_dir) / f"{student_id}.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except Exception:
        log.exception("failed to read %s", path)
        return []


def _f(value: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def write_markdown(student_id: str, log_dir: str = "trading-logs") -> Optional[str]:
    """Rebuild ``student_N.md`` from the CSV.  Renders as a table on GitHub."""
    try:
        rows = read_rows(student_id, log_dir)
        path = Path(log_dir) / f"{student_id}.md"
        if not rows:
            path.write_text(f"# {student_id} — daily trading log\n\n_No runs yet._\n", "utf-8")
            return path.as_posix()

        equities = [(_f(r.get("equity", "")), r) for r in rows]
        valid = [(e, r) for e, r in equities if math.isfinite(e)]
        day_moves = [(_f(r.get("day_pl_pct", "")), r) for r in rows]
        valid_days = [(d, r) for d, r in day_moves if math.isfinite(d)]

        latest = rows[-1]
        # Summary figures come from the most recent row that actually HAS an
        # equity reading, so a trailing "account unreadable" row does not blank
        # out the whole header while still appearing in the history table.
        last_valid = valid[-1][1] if valid else latest
        total_pl = _f(last_valid.get("total_pl", ""))
        total_pl_pct = _f(last_valid.get("total_pl_pct", ""))
        up_days = sum(1 for d, _ in valid_days if d > 0)
        down_days = sum(1 for d, _ in valid_days if d < 0)
        flat_days = sum(1 for d, _ in valid_days if d == 0)

        best = max(valid_days, key=lambda t: t[0]) if valid_days else None
        worst = min(valid_days, key=lambda t: t[0]) if valid_days else None
        peak = max(valid, key=lambda t: t[0]) if valid else None

        out: List[str] = [
            f"# {student_id} — daily trading log",
            "",
            "Appended once per run by the trading pipeline and committed back to the "
            "repository by GitHub Actions, so the 15-20 day history survives the runner.",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Runs recorded | {len(rows)} |",
            f"| Latest equity | {_fmt_money(_f(last_valid.get('equity','')))}"
            + (f" (as of {last_valid.get('date','')})" if last_valid is not latest else "")
            + " |",
            f"| Total P&L | {_fmt_money(total_pl)} |",
            f"| Total P&L % | {_fmt_pct(total_pl_pct)} |",
            f"| Best day | {_fmt_day(best)} |",
            f"| Worst day | {_fmt_day(worst)} |",
            f"| Peak equity | {_fmt_money(peak[0]) if peak else 'n/a'}"
            + (f" on {peak[1].get('date','')}" if peak else "")
            + " |",
            f"| Up days | {up_days} |",
            f"| Down days | {down_days} |",
            f"| Flat days | {flat_days} |",
            f"| Last data source | {latest.get('data_source','')} |",
            f"| Last engine | {latest.get('engine','')} |",
            "",
            "## Daily history",
            "",
            "| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | "
            "Total P&L | Total % | Pos | B/S/H | Orders | Data | Engine | Mode |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in rows:
            ts = r.get("timestamp_utc", "")
            time_part = ts.split("T")[1][:5] if "T" in ts else ""
            out.append(
                "| {date} | {t} | {eq} | {cash} | {bp} | {dpl} | {dpct} | {tpl} | "
                "{tpct} | {pos} | {b}/{s}/{h} | {ord} | {src} | {eng} | {mode} |".format(
                    date=r.get("date", ""),
                    t=time_part,
                    eq=_fmt_money(_f(r.get("equity", ""))),
                    cash=_fmt_money(_f(r.get("cash", ""))),
                    bp=_fmt_money(_f(r.get("buying_power", ""))),
                    dpl=_fmt_money(_f(r.get("day_pl", ""))),
                    dpct=_fmt_pct(_f(r.get("day_pl_pct", ""))),
                    tpl=_fmt_money(_f(r.get("total_pl", ""))),
                    tpct=_fmt_pct(_f(r.get("total_pl_pct", ""))),
                    pos=r.get("open_positions", ""),
                    b=r.get("buy_signals", ""),
                    s=r.get("sell_signals", ""),
                    h=r.get("hold_signals", ""),
                    ord=r.get("orders_submitted", ""),
                    src=r.get("data_source", ""),
                    eng=r.get("engine", ""),
                    mode=r.get("mode", ""),
                )
            )
        notes = [r.get("notes", "") for r in rows if (r.get("notes") or "").strip()]
        if notes:
            out += ["", "## Notes", ""]
            out += [f"- {n}" for n in notes[-15:]]
        out.append("")
        path.write_text("\n".join(out), encoding="utf-8")
        return path.as_posix()
    except Exception:
        log.exception("failed to write markdown log for %s", student_id)
        return None


def _fmt_money(v: float) -> str:
    return "n/a" if not math.isfinite(v) else f"${v:,.2f}"


def _fmt_pct(v: float) -> str:
    return "n/a" if not math.isfinite(v) else f"{v:+.2f}%"


def _fmt_day(entry) -> str:
    if not entry:
        return "n/a"
    pct, row = entry
    return f"{pct:+.2f}% on {row.get('date','')}"
