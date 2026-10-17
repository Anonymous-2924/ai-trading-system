"""End-to-end orchestration for one student, one run.

Order of operations
-------------------
1. Batched OHLCV for the whole universe in ONE Alpaca request.
2. News for the whole universe in ONE request.
3. The deterministic rule engine over every symbol — always, unconditionally.
   This is the baseline and it is what the system falls back to.
4. The CrewAI crew, if an LLM is configured.  Its decisions OVERRIDE the rule
   engine per symbol.  If it fails for any reason the fallback is ANNOUNCED,
   never silent.
5. Risk sizing, exits before entries.
6. Order submission, only when mode=execute AND REQUIRE_HUMAN_APPROVAL=false.
7. Artefacts to ``model-run/`` and one row appended to the member's daily log
   — even if the account could not be read, and even if something failed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import daily_log
from .agents import CrewRunResult, run_crew
from .alpaca_client import AlpacaClient, AlpacaError, MarketDataUnavailable, build_client
from .config import AppConfig, StudentConfig
from .paper_guard import PaperTradingViolation
from .risk import PlanResult, plan_orders
from .rule_engine import RuleEngineResult, run_rule_engine
from .run_logger import RunLogger
from .scoring import Signal

log = logging.getLogger(__name__)

RULE_ENGINE = "deterministic_rule_engine"
CREW_ENGINE = "crewai_agents"


@dataclass
class RunResult:
    student_id: str
    engine: str = RULE_ENGINE
    data_source: str = "UNAVAILABLE"
    counts: Dict[str, int] = field(default_factory=dict)
    signals: List[dict] = field(default_factory=list)
    plan: Optional[PlanResult] = None
    submitted: List[dict] = field(default_factory=list)
    account: Optional[dict] = None
    positions: List[dict] = field(default_factory=list)
    fallbacks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    artefacts: List[str] = field(default_factory=list)
    log_status: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "engine": self.engine,
            "data_source": self.data_source,
            "counts": self.counts,
            "signals": self.signals,
            "plan": self.plan.to_dict() if self.plan else None,
            "orders_submitted": self.submitted,
            "account": self.account,
            "position_count": len(self.positions),
            "fallbacks": self.fallbacks,
            "errors": self.errors,
            "notes": self.notes,
            "artefacts": self.artefacts,
            "log_status": self.log_status,
        }

    def summary_lines(self) -> List[str]:
        out = [
            f"=== {self.student_id} ===",
            f"engine       : {self.engine}",
            f"data source  : {self.data_source}",
            f"signals      : {self.counts}",
        ]
        if self.account:
            out.append(
                "equity       : ${:,.2f}  (day {:+,.2f}, total {:+,.2f})".format(
                    float(self.account.get("equity") or 0.0),
                    float(self.account.get("equity") or 0.0)
                    - float(self.account.get("last_equity") or 0.0),
                    float(self.account.get("equity") or 0.0)
                    - float(self.account.get("starting_equity") or 0.0),
                )
            )
        if self.plan:
            buys = [o for o in self.plan.orders if o.side == "buy"]
            sells = [o for o in self.plan.orders if o.side == "sell"]
            out.append(f"planned      : {len(sells)} exit(s), {len(buys)} entry(ies)")
            for o in self.plan.orders[:12]:
                out.append(
                    f"  {o.side.upper():4s} {o.symbol:6s} {o.qty:>10.3f} @ ~${o.price:,.2f}"
                    f"  (${o.notional:,.0f}, {o.conviction})"
                )
        out.append(f"submitted    : {len(self.submitted)}")
        for fb in self.fallbacks:
            out.append(f"FALLBACK     : {fb}")
        for err in self.errors:
            out.append(f"ERROR        : {err}")
        return out


def _config_snapshot(cfg: AppConfig, student: StudentConfig) -> dict:
    return {
        "student": student.id,
        "mode": cfg.mode,
        "demo_mode": cfg.demo_mode,
        "require_human_approval": cfg.require_human_approval,
        "auto_execute": cfg.execute,
        "aggression": cfg.aggression,
        "max_llm_symbols": cfg.max_llm_symbols,
        "lookback_days": cfg.lookback_days,
        "llm": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "max_retries": cfg.llm.max_retries,
            "api_key_present": bool(cfg.llm.api_key),
        },
        "risk": {
            "position_pct": round(cfg.risk.position_pct, 4),
            "max_positions": cfg.risk.max_positions,
            "max_gross_exposure": round(cfg.risk.max_gross_exposure, 4),
            "max_position_pct": round(cfg.risk.max_position_pct, 4),
            "max_sector_pct": round(cfg.risk.max_sector_pct, 4),
            "atr_stop_multiple": round(cfg.risk.atr_stop_multiple, 3),
            "atr_target_multiple": round(cfg.risk.atr_target_multiple, 3),
            "min_high_beta_pct": cfg.risk.min_high_beta_pct,
        },
        "signals": cfg.signals,
        "universe": student.symbols,
        "high_beta": student.high_beta,
    }


def _merge_llm_decisions(
    rule_result: RuleEngineResult, crew: CrewRunResult
) -> tuple[List[Signal], List[str]]:
    """LLM decisions override the rule engine per symbol; the rest stand."""
    by_symbol = rule_result.by_symbol()
    notes: List[str] = []
    for d in crew.decisions:
        sym = d["symbol"]
        sig = by_symbol.get(sym)
        if sig is None:
            notes.append(f"{sym}: LLM returned a decision for a symbol with no features; ignored")
            continue
        if d["action"] != sig.action:
            notes.append(
                f"{sym}: LLM overrode the rule engine {sig.action} -> {d['action']} "
                f"({d['conviction']}) — {d['rationale'][:140]}"
            )
        sig.action = d["action"]
        sig.conviction = d["conviction"]
        sig.rationale.append(f"  LLM: {d['action']} / {d['conviction']} — {d['rationale'][:300]}")
    decided = {d["symbol"] for d in crew.decisions}
    undecided = [s for s in by_symbol if s not in decided]
    if undecided:
        notes.append(
            f"{len(undecided)} symbol(s) not covered by the crew kept their rule-engine "
            f"decision: {', '.join(sorted(undecided)[:20])}"
        )
    return list(by_symbol.values()), notes


def run_for_student(
    cfg: AppConfig,
    student_id: str,
    symbols: Optional[Sequence[str]] = None,
    use_llm: bool = True,
    run_logger: Optional[RunLogger] = None,
) -> RunResult:
    """Run the whole pipeline for one student.  Always returns a RunResult."""
    student = cfg.student(student_id)
    result = RunResult(student_id=student.id)
    syms = [s.upper() for s in (symbols or student.symbols)]
    rl = run_logger or RunLogger(
        directory=cfg.model_run_dir, config_snapshot=_config_snapshot(cfg, student)
    )
    rl.config_snapshot = rl.config_snapshot or _config_snapshot(cfg, student)

    client: Optional[AlpacaClient] = None
    bars: Dict[str, Any] = {}
    articles: List[dict] = []

    # --- 1 & 2: market data and news, batched ---------------------------
    try:
        client = build_client(cfg, student)
        result.data_source = client.data_source
        bars = client.get_bars(syms, days=cfg.lookback_days)
        result.notes.append(
            f"OHLCV for {len(bars)}/{len(syms)} symbols in "
            f"{client.last_request_count} HTTP request(s)"
        )
    except (MarketDataUnavailable, PaperTradingViolation, AlpacaError) as exc:
        result.errors.append(f"market data: {exc}")
        log.error("market data failed for %s: %s", student.id, exc)

    if client is not None and bars:
        try:
            hours = int((cfg.sentiment or {}).get("lookback_hours", 48))
            articles = client.get_news(syms, hours=hours)
            result.notes.append(f"{len(articles)} news article(s) in the last {hours}h")
        except (MarketDataUnavailable, AlpacaError) as exc:
            result.notes.append(f"news unavailable ({exc}); sentiment is neutral")

    rl.write(
        "Market Data Agent",
        summary=f"Batched OHLCV + news for {student.id}",
        indicators={"symbols": syms, "lookback_days": cfg.lookback_days},
        results={
            "symbols_returned": sorted(bars),
            "symbols_missing": sorted(set(syms) - set(bars)),
            "http_requests": getattr(client, "last_request_count", 0),
            "news_articles": len(articles),
            "data_source": result.data_source,
        },
        errors=result.errors or None,
    )

    if not bars:
        result.errors.append("no market data; cannot produce signals this run")
        _finalise(cfg, student, result, client, rl)
        return result

    # --- 3: the deterministic rule engine, always -----------------------
    rule_result = run_rule_engine(syms, bars, articles, cfg)
    result.notes.extend(rule_result.notes)
    rl.write(
        "Technical Analysis Agent",
        summary="Deterministic feature extraction across all five dimensions",
        indicators={
            sym: fs.values for sym, fs in list(rule_result.features.items())[:50]
        },
        decisions={s.symbol: s.action for s in rule_result.signals},
        results={"skipped": rule_result.skipped},
    )
    rl.write(
        "Quantitative Analysis Agent",
        summary="Weighted ensemble composite scores (reference decisions)",
        indicators={"dimension_weights": (cfg.signals or {}).get("dimension_weights")},
        decisions=[s.to_dict() for s in rule_result.signals],
        results={"counts": rule_result.counts},
    )
    rl.write(
        "News Sentiment Agent",
        summary="Lexicon sentiment over real headlines (never fabricated)",
        indicators={"article_count": len(articles)},
        decisions={k: v.to_dict() for k, v in rule_result.sentiment.items()},
        results={
            "policy": "symbols with no news score neutral and are flagged NO_NEWS_DATA"
        },
    )

    signals = list(rule_result.signals)
    result.engine = RULE_ENGINE

    # --- 4: the crew, if an LLM is configured ---------------------------
    if use_llm and (cfg.llm.provider or "").lower() != "none":
        crew = run_crew(cfg, student, [s.symbol for s in signals], run_logger=rl)
        if crew.ok:
            result.engine = CREW_ENGINE
            signals, merge_notes = _merge_llm_decisions(rule_result, crew)
            result.notes.extend(merge_notes)
        else:
            # ANNOUNCE the fallback — loudly, in three places.
            message = (
                f"LLM path unavailable, using the deterministic rule engine: "
                f"{crew.fallback_reason}"
            )
            result.fallbacks.append(message)
            result.engine = RULE_ENGINE
            log.warning(message)
            print(f"!! FALLBACK ({student.id}): {message}", flush=True)
            # The final artefact is written once, at the end of the run, and it
            # carries this announcement — see the `fallbacks` block there.
            crew_errors = crew.errors or [crew.fallback_reason]
    else:
        result.notes.append(
            "LLM disabled for this run (provider=none or --no-llm); the "
            "deterministic rule engine decides everything."
        )

    result.counts = {
        "BUY": sum(1 for s in signals if s.action == "BUY"),
        "SELL": sum(1 for s in signals if s.action == "SELL"),
        "HOLD": sum(1 for s in signals if s.action == "HOLD"),
    }
    result.signals = [s.to_dict() for s in signals]

    # --- 5: risk sizing -------------------------------------------------
    account, positions = None, []
    try:
        if client is not None:
            account = client.get_account()
            positions = client.get_positions()
    except (MarketDataUnavailable, AlpacaError) as exc:
        result.errors.append(f"account/positions: {exc}")

    result.positions = positions
    equity = float((account or {}).get("equity") or student.starting_equity)
    cash = float((account or {}).get("cash") or student.starting_equity)
    buying_power = float((account or {}).get("buying_power") or cash)

    plan = plan_orders(
        student_id=student.id,
        signals=signals,
        positions=positions,
        equity=equity,
        cash=cash,
        buying_power=buying_power,
        risk=cfg.risk,
        sector_of=cfg.sector_of,
        high_beta_symbols=student.high_beta,
        atr_by_symbol=rule_result.atr_map(),
        price_by_symbol=rule_result.price_map(),
    )
    result.plan = plan
    result.notes.extend(plan.notes)
    rl.write(
        "Risk Management Agent",
        summary=(
            f"Sized against ${equity:,.0f} equity at aggression {cfg.aggression:.2f}; "
            "exits processed before entries"
        ),
        indicators={"atr14": rule_result.atr_map()},
        decisions=plan.to_dict(),
        results={
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
            "gross_exposure_after": round(plan.gross_exposure_after, 4),
        },
    )

    # --- 6: submission --------------------------------------------------
    if not cfg.execute:
        result.notes.append(
            f"orders NOT submitted: mode={cfg.mode}, "
            f"require_human_approval={cfg.require_human_approval}. "
            "Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false."
        )
    elif client is None:
        result.errors.append("cannot submit orders: no Alpaca client")
    else:
        for order in plan.orders:
            try:
                res = client.submit_order(
                    order.symbol,
                    order.qty,
                    order.side,
                    order.client_order_id,
                )
                result.submitted.append(res)
            except (PaperTradingViolation, MarketDataUnavailable) as exc:
                result.errors.append(f"{order.symbol}: BLOCKED {exc}")
                log.error("order blocked for %s: %s", order.symbol, exc)
            except AlpacaError as exc:
                result.errors.append(f"{order.symbol}: order failed {exc}")

    fallback_banner = ""
    if result.fallbacks:
        fallback_banner = "\n\n**LLM FALLBACK** — decisions come from the " \
            "deterministic rule engine:\n" + "\n".join(f"- {f}" for f in result.fallbacks)
    rl.write(
        "Final Decision Agent",
        summary=f"Final decisions for {student.id} via {result.engine}" + fallback_banner,
        indicators={"engine": result.engine},
        decisions=result.signals,
        results={
            "planned_orders": [o.to_dict() for o in plan.orders],
            "submitted": result.submitted,
            "auto_execute": cfg.execute,
            "fallbacks": result.fallbacks,
        },
        errors=(result.errors + result.fallbacks) or None,
    )

    _finalise(cfg, student, result, client, rl, account)
    return result


def _finalise(
    cfg: AppConfig,
    student: StudentConfig,
    result: RunResult,
    client: Optional[AlpacaClient],
    rl: RunLogger,
    account: Optional[dict] = None,
) -> None:
    """Append the daily-log row.  Runs even when everything above failed."""
    if account is None and client is not None:
        try:
            account = client.get_account()
        except Exception:
            account = None
    result.account = dict(account) if account else None
    if result.account is not None:
        result.account.setdefault("starting_equity", student.starting_equity)

    notes = "; ".join((result.fallbacks + result.errors + result.notes))[:500]
    row = daily_log.build_row(
        student_id=student.id,
        starting_equity=student.starting_equity,
        account=account,
        counts=result.counts,
        open_positions=len(result.positions),
        orders_submitted=len([o for o in result.submitted if o.get("submitted")]),
        data_source=result.data_source,
        engine=result.engine,
        mode=cfg.mode,
        notes=notes,
    )
    result.log_status = daily_log.append_row(row, cfg.log_dir)
    if not result.log_status.get("ok"):
        # A logging failure is reported but never raised: it must not break a
        # trading run.
        result.errors.append(f"daily log failed: {result.log_status.get('error')}")
    result.artefacts = list(rl.written)


def run_all(
    cfg: AppConfig,
    student_ids: Optional[Sequence[str]] = None,
    symbols: Optional[Sequence[str]] = None,
    use_llm: bool = True,
) -> List[RunResult]:
    ids = list(student_ids) if student_ids else [s.id for s in cfg.students]
    out: List[RunResult] = []
    for sid in ids:
        try:
            out.append(run_for_student(cfg, sid, symbols, use_llm))
        except KeyError as exc:
            log.error("skipping unknown student: %s", exc)
        except Exception as exc:  # one student must not sink the rest
            log.exception("run failed for %s", sid)
            failed = RunResult(student_id=sid)
            failed.errors.append(f"{type(exc).__name__}: {exc}")
            out.append(failed)
    return out
