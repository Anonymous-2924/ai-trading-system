#!/usr/bin/env python3
"""Ask Alpaca directly what each student's keys actually see.

Written to answer one question: the pipeline reported orders as submitted,
but nothing appears on the Alpaca dashboard. Either the keys point at a
different paper account than the browser is showing, or the orders were
accepted and then rejected asynchronously. This prints the account NUMBER
each key pair belongs to, plus every order Alpaca has on file with its
status, so the two can be compared directly.

    python scripts/check_alpaca.py
    python scripts/check_alpaca.py --students student_1 --limit 50
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system.alpaca_client import (  # noqa: E402
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.config import load_config  # noqa: E402
from trading_system.paper_guard import PaperTradingViolation  # noqa: E402


def money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def report(cfg, student, limit: int) -> bool:
    print("=" * 78)
    print(f"{student.id}  ({student.name})")
    print("=" * 78)

    key, secret = student.credentials()
    if not (key and secret):
        print(f"  NO CREDENTIALS. Set {student.key_env} and {student.secret_env}.")
        print()
        return False

    # Never print the key. Show just enough to tell three keys apart.
    print(f"  key env   : {student.key_env}")
    print(f"  key        : {key[:4]}...{key[-4:]}  (length {len(key)})")

    client = build_client(cfg, student, demo_override=False)
    print(f"  endpoint   : {client.base_url}")

    try:
        account = client.get_account()
    except (MarketDataUnavailable, AlpacaError, PaperTradingViolation) as exc:
        print(f"  ACCOUNT READ FAILED: {exc}")
        print()
        return False

    # THE KEY LINE: match this against the account number shown in the
    # browser's top-left corner on app.alpaca.markets.
    print(f"  ACCOUNT NUMBER : {account.get('account_number')}   <-- compare with the dashboard")
    print(f"  status         : {account.get('status')}")
    print(f"  equity         : {money(account.get('equity'))}")
    print(f"  last_equity    : {money(account.get('last_equity'))}")
    print(f"  cash           : {money(account.get('cash'))}")
    print(f"  buying power   : {money(account.get('buying_power'))}")

    try:
        positions = client.get_positions()
    except (AlpacaError, MarketDataUnavailable) as exc:
        positions = []
        print(f"  positions read failed: {exc}")
    print(f"  open positions : {len(positions)}")
    for p in positions:
        print(
            f"      {p['symbol']:6s} qty {p['qty']:>10.3f}  "
            f"mkt {money(p['market_value']):>12s}  P&L {money(p['unrealized_pl'])}"
        )

    try:
        orders = client.get_orders(status="all", limit=limit)
    except (AlpacaError, MarketDataUnavailable) as exc:
        print(f"  ORDERS READ FAILED: {exc}")
        print()
        return False

    print(f"  orders on file : {len(orders)}  (status=all, limit={limit})")
    if not orders:
        print("      NONE. Alpaca has no record of any order on this account.")
        print("      If the pipeline said 'submitted', the keys belong to a")
        print("      DIFFERENT paper account than the one you are looking at.")
    else:
        by_status = Counter(str(o.get("status")) for o in orders)
        print(f"      by status: {dict(by_status)}")
        print()
        print(
            f"      {'symbol':<8}{'side':<6}{'qty':>10}  {'filled':>10}  "
            f"{'status':<18}{'submitted_at':<22}"
        )
        for o in orders[:limit]:
            print(
                f"      {str(o.get('symbol')):<8}{str(o.get('side')):<6}"
                f"{str(o.get('qty')):>10}  {str(o.get('filled_qty')):>10}  "
                f"{str(o.get('status')):<18}{str(o.get('submitted_at'))[:19]:<22}"
            )
            # A rejected order carries the reason Alpaca refused it.
            for field in ("reject_reason", "failed_at", "canceled_at", "expired_at"):
                if o.get(field):
                    print(f"          {field}: {o.get(field)}")
    print()
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect each student's Alpaca paper account")
    p.add_argument("--config", default=None)
    p.add_argument("--students", default="", help="comma-separated ids; default all")
    p.add_argument("--limit", type=int, default=25, help="how many orders to list")
    args = p.parse_args()

    cfg = load_config(args.config)

    print()
    print(f"config loaded from  : {cfg.config_path}")
    print(f"students defined    : {[s.id for s in cfg.students] or 'NONE'}")
    print(f"Alpaca endpoint     : {cfg.alpaca_base_url}")
    print()

    if not cfg.students:
        print("ERROR: the config defines no students, so there is nothing to")
        print(f"       inspect. Check that {cfg.config_path} exists and has a")
        print("       'students:' section.")
        return 2

    # "all", "*", "universe" and blank all mean everyone — the trading
    # workflow's students input defaults to "all", so accept the same word.
    raw = (args.students or "").strip().lower()
    if raw in {"", "all", "*", "universe"}:
        students = list(cfg.students)
    else:
        wanted = [x.strip().lower() for x in raw.split(",") if x.strip()]
        known = {s.id.lower(): s for s in cfg.students}
        unknown = [w for w in wanted if w not in known]
        if unknown:
            print(f"ERROR: unknown student id(s): {', '.join(unknown)}")
            print(f"       known ids: {', '.join(known)}")
            print("       Leave the box blank or type 'all' for everyone.")
            return 2
        students = [known[w] for w in wanted]

    print("Open app.alpaca.markets and compare the account number in the")
    print("top-left corner against the ACCOUNT NUMBER printed below.")
    print()

    ok = [report(cfg, s, args.limit) for s in students]

    print("=" * 78)
    numbers = []
    for s in students:
        key, secret = s.credentials()
        numbers.append((s.id, bool(key and secret)))
    print("credentials present:", {sid: present for sid, present in numbers})
    print(f"{sum(ok)}/{len(students)} account(s) read successfully")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
