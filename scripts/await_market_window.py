#!/usr/bin/env python3
"""Wait until the right point in the US trading session, or report why not.

GitHub's scheduler is best-effort — we have measured delays of over three
hours — and the US close moves an hour when the clocks change in November.
Between them, a fixed UTC cron cannot reliably mean "30 minutes before the
close".

So the workflow fires EARLY and this script decides what to actually do. It
asks Alpaca when the session opens and closes, works out the target moment,
and then either waits for it, says "go now" if we arrived late but the market
is still open, or reports that the window is gone.

    python scripts/await_market_window.py --window open
    python scripts/await_market_window.py --window close --max-wait 3600

Exit codes:
    0  it is time to trade
    10 the window is gone (weekend, holiday, or we arrived too late)
    1  could not reach Alpaca to find out
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system.alpaca_client import (  # noqa: E402
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.config import load_config  # noqa: E402
from trading_system.paper_guard import PaperTradingViolation  # noqa: E402

#: Minutes after the open for the morning run. The 09:30-09:45 opening range
#: must have formed AND settled past the data feed's delay before the
#: opening-range and relative-volume features mean anything.
OPEN_OFFSET_MINUTES = 35

#: Minutes before the close for the afternoon run.
CLOSE_OFFSET_MINUTES = 30

#: How late is too late. Past this many minutes beyond the target we would be
#: trading at a materially different point in the session than intended.
OPEN_GRACE_MINUTES = 85     # 10:05 target -> usable until ~11:30 ET
CLOSE_GRACE_MINUTES = 25    # 15:30 target -> usable until ~15:55 ET


def eastern_offset(moment: datetime) -> timedelta:
    """US Eastern offset from UTC for a given instant.

    Derived from Alpaca's own session times rather than a timezone database,
    so there is nothing local to keep up to date.
    """
    return timedelta(hours=-4) if is_daylight(moment) else timedelta(hours=-5)


def is_daylight(moment: datetime) -> bool:
    """US daylight saving: second Sunday in March to first Sunday in November."""
    year = moment.year
    march = datetime(year, 3, 8, tzinfo=timezone.utc)
    start = march + timedelta(days=(6 - march.weekday()) % 7)      # 2nd Sunday
    november = datetime(year, 11, 1, tzinfo=timezone.utc)
    end = november + timedelta(days=(6 - november.weekday()) % 7)  # 1st Sunday
    return start <= moment < end


def session_bounds(client, now: datetime):
    """(open, close) as UTC datetimes for today's session, or None."""
    today = now.strftime("%Y-%m-%d")
    try:
        days = client.get_calendar(today, today)
    except (MarketDataUnavailable, AlpacaError, PaperTradingViolation) as exc:
        print(f"could not read the market calendar: {exc}")
        return None
    if not days:
        return None

    session = days[0]
    offset = eastern_offset(now)

    def to_utc(hhmm: str) -> datetime:
        hour, minute = (int(x) for x in hhmm.split(":"))
        local = datetime.combine(now.date(), dtime(hour, minute), tzinfo=timezone.utc)
        return local - offset  # Eastern wall clock -> UTC

    try:
        return to_utc(session["open"]), to_utc(session["close"])
    except (ValueError, KeyError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for the right trading window")
    parser.add_argument("--window", choices=["open", "close"], required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--max-wait", type=int, default=3600,
        help="seconds we are willing to sleep before giving up",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report the decision without actually sleeping",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    client = build_client(cfg, cfg.students[0])
    now = datetime.now(timezone.utc)

    bounds = session_bounds(client, now)
    if bounds is None:
        print(f"No US trading session today ({now:%Y-%m-%d}) — weekend or holiday.")
        return 10
    market_open, market_close = bounds

    if args.window == "open":
        target = market_open + timedelta(minutes=OPEN_OFFSET_MINUTES)
        grace = timedelta(minutes=OPEN_GRACE_MINUTES)
    else:
        target = market_close - timedelta(minutes=CLOSE_OFFSET_MINUTES)
        grace = timedelta(minutes=CLOSE_GRACE_MINUTES)

    offset = eastern_offset(now)

    def et(moment: datetime) -> str:
        return (moment + offset).strftime("%H:%M ET")

    print(f"now           : {now:%Y-%m-%d %H:%M} UTC ({et(now)})")
    print(f"session       : {et(market_open)} - {et(market_close)}")
    print(f"target window : {et(target)}  (+/- grace {grace})")

    if now > target + grace:
        print(f"MISSED: we are {now - target} past the target. Skipping this run.")
        return 10

    if now >= target:
        print("GO: at or just past the target, and still inside the window.")
        return 0

    wait = (target - now).total_seconds()
    if wait > args.max_wait:
        print(
            f"WAIT TOO LONG: {wait / 60:.0f} minutes until the target, limit is "
            f"{args.max_wait / 60:.0f}. Skipping rather than burning a runner."
        )
        return 10

    print(f"WAITING {wait / 60:.1f} minutes until {et(target)}...")
    if args.dry_run:
        print("(dry run, not sleeping)")
        return 0
    time.sleep(wait)
    print(f"GO: reached {datetime.now(timezone.utc):%H:%M} UTC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
