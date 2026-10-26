"""Per-member alpha history, appended once per run beside the daily log.

``daily_log`` answers "where is the account". ``trade_ledger`` answers "what
did we buy". This answers "was any of it skill" — a time series of excess
return, Jensen's alpha and the information coefficient, so the measures can
be watched moving rather than only read once at the end.

One pair of files per member, committed to the repository exactly like the
daily log:

    trading-logs/alpha_student_1.csv   +   alpha_student_1.md

As with the other logs, a failure here never breaks a trading run.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

#: Append-only. Never reorder, or existing history stops lining up.
COLUMNS: List[str] = [
    "timestamp_utc",
    "date",
    "student_id",
    "run_label",
    "trades",
    "open_trades",
    "closed_trades",
    "mean_return_pct",
    "mean_excess_pct",
    "mean_jensen_pct",
    "total_pnl",
    "win_rate_pct",
    "ic_return",
    "ic_excess",
    "benchmark",
    "data_source",
    "note",
]


def _num(value, places: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if not math.isfinite(f) else f"{f:.{places}f}"


@dataclass
class AlphaRow:
    timestamp_utc: str = ""
    date: str = ""
    student_id: str = ""
    run_label: str = ""
    trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    mean_return_pct: float = float("nan")
    mean_excess_pct: float = float("nan")
    mean_jensen_pct: float = float("nan")
    total_pnl: float = float("nan")
    win_rate_pct: float = float("nan")
    ic_return: float = float("nan")
    ic_excess: float = float("nan")
    benchmark: str = "SPY"
    data_source: str = ""
    note: str = ""

    def as_csv_dict(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key in COLUMNS:
            value = getattr(self, key, "")
            if isinstance(value, float):
                out[key] = _num(value)
            else:
                out[key] = str(value).replace("\n", " ").replace("\r", " ")
        return out


def build_row(
    *,
    student_id: str,
    summary,
    run_label: str = "",
    data_source: str = "",
    benchmark: str = "SPY",
    note: str = "",
    when: Optional[datetime] = None,
) -> AlphaRow:
    """Turn an ``alpha.Summary`` into a log row."""
    when = when or datetime.now(timezone.utc)
    return AlphaRow(
        timestamp_utc=when.isoformat(timespec="seconds"),
        date=when.strftime("%Y-%m-%d"),
        student_id=student_id,
        run_label=run_label,
        trades=int(summary.trades),
        open_trades=int(summary.open_trades),
        closed_trades=int(summary.trades - summary.open_trades),
        mean_return_pct=summary.mean_return,
        mean_excess_pct=summary.mean_excess,
        mean_jensen_pct=summary.mean_jensen,
        total_pnl=summary.total_pnl,
        win_rate_pct=summary.win_rate,
        ic_return=summary.ic_return,
        ic_excess=summary.ic_excess,
        benchmark=benchmark,
        data_source=data_source,
        note=note,
    )


def append_row(row: AlphaRow, log_dir: str = "trading-logs") -> Dict[str, object]:
    """Append to the CSV and rebuild the Markdown mirror.  Never raises."""
    status: Dict[str, object] = {"ok": False, "csv": "", "md": "", "error": ""}
    try:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        csv_path = directory / f"alpha_{row.student_id}.csv"
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
        log.exception("failed to append alpha log row")
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


def read_rows(student_id: str, log_dir: str = "trading-logs") -> List[Dict[str, str]]:
    path = Path(log_dir) / f"alpha_{student_id}.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except Exception:
        log.exception("failed to read %s", path)
        return []


def _f(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def _pct(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"{value:+.2f}%"


def _money(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"${value:,.2f}"


def write_markdown(student_id: str, log_dir: str = "trading-logs") -> Optional[str]:
    """Rebuild ``alpha_student_N.md`` from the CSV.  Renders on GitHub."""
    try:
        rows = read_rows(student_id, log_dir)
        path = Path(log_dir) / f"alpha_{student_id}.md"
        if not rows:
            path.write_text(
                f"# {student_id} — alpha history\n\n_No trades measured yet._\n",
                encoding="utf-8",
            )
            return path.as_posix()

        latest = rows[-1]
        trades = int(_f(latest.get("trades", 0)) or 0)

        out: List[str] = [
            f"# {student_id} — alpha history",
            "",
            "Appended once per run, beside the daily log. Measures whether the "
            "trades we made actually earned anything:",
            "",
            "- **Excess return** — our return minus the benchmark's over the same "
            "window. Did we beat the market on the names we picked?",
            "- **Jensen's alpha** — our return minus beta x the benchmark's. Did we "
            "beat it *after adjusting for the risk taken*? The stricter test, and "
            "the honest one for a deliberately high-beta book.",
            "- **Information coefficient (IC)** — correlation between the composite "
            "score at entry and the realised return. Do the indicators predict "
            "anything?",
            "",
            "## Latest",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Trades measured | {trades} ({int(_f(latest.get('open_trades', 0)) or 0)} still open) |",
            f"| Mean return | {_pct(_f(latest.get('mean_return_pct')))} |",
            f"| Mean excess vs {latest.get('benchmark', 'SPY')} | {_pct(_f(latest.get('mean_excess_pct')))} |",
            f"| Mean Jensen's alpha | {_pct(_f(latest.get('mean_jensen_pct')))} |",
            f"| Total P&L on these trades | {_money(_f(latest.get('total_pnl')))} |",
            f"| Win rate | {_pct(_f(latest.get('win_rate_pct'))).replace('+', '')} |",
            f"| Signal IC | {_f(latest.get('ic_return')):+.3f}"
            if math.isfinite(_f(latest.get("ic_return")))
            else "| Signal IC | n/a",
            "",
        ]
        # close the IC row properly whichever branch was taken
        if not out[-2].endswith("|"):
            out[-2] = out[-2] + " |"

        if trades < 30:
            out += [
                f"> **Small sample.** {trades} trades. Significance needs 30+ as a "
                "bare minimum and realistically hundreds, and beta is itself noisy "
                "over a short period. These numbers describe what happened; they do "
                "not establish whether the strategy works.",
                "",
            ]

        out += [
            "## History",
            "",
            "| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | "
            "Win rate | IC | Total P&L | Data |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in rows:
            ts = r.get("timestamp_utc", "")
            ic = _f(r.get("ic_return"))
            out.append(
                "| {date} | {t} | {label} | {trades} | {open} | {ret} | {exc} | "
                "{jen} | {win} | {ic} | {pnl} | {src} |".format(
                    date=r.get("date", ""),
                    t=ts.split("T")[1][:5] if "T" in ts else "",
                    label=r.get("run_label", "") or "—",
                    trades=r.get("trades", ""),
                    open=r.get("open_trades", ""),
                    ret=_pct(_f(r.get("mean_return_pct"))),
                    exc=_pct(_f(r.get("mean_excess_pct"))),
                    jen=_pct(_f(r.get("mean_jensen_pct"))),
                    win=_pct(_f(r.get("win_rate_pct"))).replace("+", ""),
                    ic=f"{ic:+.3f}" if math.isfinite(ic) else "n/a",
                    pnl=_money(_f(r.get("total_pnl"))),
                    src=r.get("data_source", ""),
                )
            )

        notes = [r.get("note", "") for r in rows if (r.get("note") or "").strip()]
        if notes:
            out += ["", "## Notes", ""] + [f"- {n}" for n in dict.fromkeys(notes[-10:])]
        out.append("")
        path.write_text("\n".join(out), encoding="utf-8")
        return path.as_posix()
    except Exception:
        log.exception("failed to write alpha markdown for %s", student_id)
        return None
