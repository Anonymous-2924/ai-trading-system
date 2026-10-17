#!/usr/bin/env python3
"""Run the trading pipeline.

Examples
--------
    # Analyse only, synthetic data, no LLM — the fastest smoke test
    python scripts/run_trading.py --demo --no-llm

    # Analyse one student with real Alpaca data and the configured LLM
    python scripts/run_trading.py --students student_1

    # Actually submit paper orders (needs BOTH flags, by design)
    RUN_MODE=execute REQUIRE_HUMAN_APPROVAL=false python scripts/run_trading.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system.config import load_config  # noqa: E402
from trading_system.pipeline import run_all  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="AI paper-trading pipeline")
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--students", default="", help="comma-separated student ids")
    p.add_argument("--symbols", default="", help="override the universe (comma-separated)")
    p.add_argument("--mode", choices=["analyse", "execute"], default=None)
    p.add_argument("--demo", action="store_true", help="use clearly-labelled synthetic data")
    p.add_argument("--no-llm", action="store_true", help="rule engine only")
    p.add_argument("--max-llm-symbols", type=int, default=None)
    p.add_argument("--aggression", type=float, default=None, help="0.0 timid .. 1.0 maximal")
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Flags are applied as environment overrides BEFORE the config is read, so
    # the derived risk numbers are recomputed from the new aggression.
    if args.mode:
        os.environ["RUN_MODE"] = args.mode
    if args.demo:
        os.environ["DEMO_MODE"] = "true"
    if args.max_llm_symbols is not None:
        os.environ["MAX_LLM_SYMBOLS"] = str(args.max_llm_symbols)
    if args.aggression is not None:
        os.environ["AGGRESSION"] = str(args.aggression)

    cfg = load_config(args.config)
    students = [s.strip() for s in args.students.split(",") if s.strip()] or None
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    print(
        f"mode={cfg.mode} demo={cfg.demo_mode} aggression={cfg.aggression:.2f} "
        f"auto_execute={cfg.execute} llm={cfg.llm.provider}:{cfg.llm.model}",
        flush=True,
    )
    if cfg.execute:
        print("!! ORDERS WILL BE SUBMITTED to the Alpaca PAPER account", flush=True)

    results = run_all(cfg, students, symbols, use_llm=not args.no_llm)

    print()
    for r in results:
        print("\n".join(r.summary_lines()))
        print()

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, default=str))

    # Exit non-zero only when every student failed outright.
    return 0 if any(not r.errors or r.signals for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
