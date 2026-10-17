"""CrewAI agents and the crew that runs them.

Six agents, in the order the brief asks for: market data, technical analysis,
quantitative analysis, news and sentiment, risk management, final decisions.
They share ONE MCP server subprocess, so the batched OHLCV fetch happens once
for the whole crew.

Failure handling
----------------
Anything that stops the crew — no provider, bad key, 429 past the retry
budget, a small model looping and returning empty content — is caught here and
reported as ``CrewRunResult(ok=False, fallback_reason=...)``.  The pipeline
then runs the deterministic rule engine and ANNOUNCES the fallback in the run
log, on stdout and in the ``engine`` column of the per-member daily log.  It
is never silent.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .config import AppConfig, StudentConfig
from .llm import LLMUnavailable, build_crew_llm, is_empty_response_error
from .mcp_client import MCPExtraMissing, crewai_tools_from_mcp
from .run_logger import RunLogger

log = logging.getLogger(__name__)

AGENT_NAMES = [
    "Market Data Agent",
    "Technical Analysis Agent",
    "Quantitative Analysis Agent",
    "News Sentiment Agent",
    "Risk Management Agent",
    "Final Decision Agent",
]


@dataclass
class CrewRunResult:
    ok: bool = False
    engine: str = "crewai_agents"
    decisions: List[dict] = field(default_factory=list)
    raw_output: str = ""
    task_outputs: Dict[str, str] = field(default_factory=dict)
    fallback_reason: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "engine": self.engine,
            "decision_count": len(self.decisions),
            "decisions": self.decisions,
            "fallback_reason": self.fallback_reason,
            "errors": self.errors,
        }


def extract_json(text: str) -> Optional[Any]:
    """Pull the first JSON object or array out of a model's reply.

    Small models wrap JSON in prose or a fenced block even when told not to,
    so the parser is forgiving rather than strict.
    """
    if not text:
        return None
    cleaned = str(text).strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except ValueError:
                continue
    return None


def normalise_decisions(payload: Any) -> List[dict]:
    """Coerce whatever the final task returned into a decision list."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        for key in ("decisions", "orders", "recommendations", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        return []

    out: List[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        action = str(item.get("action") or item.get("signal") or "").strip().upper()
        if not symbol or action not in {"BUY", "SELL", "HOLD"}:
            continue
        conviction = str(item.get("conviction") or "MEDIUM").strip().upper()
        if conviction not in {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}:
            conviction = "MEDIUM"
        try:
            composite = float(item.get("composite", item.get("score", 0.0)))
        except (TypeError, ValueError):
            composite = 0.0
        out.append(
            {
                "symbol": symbol,
                "action": action,
                "conviction": conviction,
                "composite": composite,
                "rationale": str(item.get("rationale") or item.get("reason") or "")[:600],
            }
        )
    return out


def build_agents(llm, tools: Sequence[Any]) -> Dict[str, Any]:
    from crewai import Agent

    common = dict(llm=llm, tools=list(tools), verbose=False, allow_delegation=False)
    return {
        "market_data": Agent(
            role="Market Data Agent",
            goal=(
                "Fetch the student's whole universe of daily OHLCV in a single "
                "batched request and report coverage and gaps."
            ),
            backstory=(
                "You run the data tap. You always call get_batched_ohlcv with "
                "symbols='all' exactly once — never one call per ticker — and you "
                "report plainly which symbols came back short or empty. You never "
                "invent a price."
            ),
            **common,
        ),
        "technical": Agent(
            role="Technical Analysis Agent",
            goal=(
                "Read the trend, momentum, volume and volatility features and "
                "describe what each symbol's chart is actually doing."
            ),
            backstory=(
                "You read indicators, not narratives. You know the MACD LINE "
                "versus zero is a trend statement and the HISTOGRAM is a momentum "
                "statement, and that a positive histogram inside a sustained "
                "downtrend is a bounce, not a reversal."
            ),
            **common,
        ),
        "quant": Agent(
            role="Quantitative Analysis Agent",
            goal=(
                "Cross-check the deterministic ensemble score against the raw "
                "features and flag any symbol where the two disagree."
            ),
            backstory=(
                "You are the numbers check. evaluate_rule_engine gives you the "
                "reference composite score; your job is to say where the "
                "statistics (z-score, trailing returns, skew) argue against it."
            ),
            **common,
        ),
        "sentiment": Agent(
            role="News Sentiment Agent",
            goal="Judge whether recent real headlines support or contradict the technicals.",
            backstory=(
                "You only ever discuss headlines the tools actually returned. If "
                "a symbol has no news you say so and score it neutral. You never "
                "invent, paraphrase into existence, or guess at a headline."
            ),
            **common,
        ),
        "risk": Agent(
            role="Risk Management Agent",
            goal=(
                "Size each candidate against equity, exposure caps, sector caps "
                "and ATR-based stops, and reject what does not fit."
            ),
            backstory=(
                "The mandate is deliberately aggressive — this book is meant to "
                "take risk — but aggressive is not unbounded. You use size_position "
                "for every candidate and you respect what it returns."
            ),
            **common,
        ),
        "decision": Agent(
            role="Final Decision Agent",
            goal="Produce the final BUY/SELL/HOLD list as strict JSON.",
            backstory=(
                "You synthesise the other five into one decision per symbol and "
                "emit JSON only. Long-only: a SELL on a symbol that is not held "
                "means close nothing, never short."
            ),
            **common,
        ),
    }


def build_tasks(agents: Dict[str, Any], student: StudentConfig, symbols: Sequence[str]):
    from crewai import Task

    sym_csv = ",".join(symbols)
    sid = student.id

    t_data = Task(
        description=(
            f"Call get_batched_ohlcv exactly once with student_id='{sid}' and "
            f"symbols='all'. Then call list_universe for '{sid}'. Report how many "
            "symbols returned data, which did not, and how many HTTP requests the "
            "fetch actually took."
        ),
        expected_output="A short coverage report: symbols returned, symbols missing, request count.",
        agent=agents["market_data"],
    )
    t_tech = Task(
        description=(
            f"Call compute_indicators with student_id='{sid}' and symbols='{sym_csv}'. "
            "For each symbol state the trend (EMA20/50/200 relationships, ADX, and "
            "the MACD LINE versus zero), the momentum (RSI, the MACD HISTOGRAM, ROC, "
            "TSI), volume (CMF, OBV, MFI, PVO) and volatility (ATR/NATR, Bollinger "
            "width and %B, Donchian position). Where the MACD line and histogram "
            "disagree, say which one the trend follows."
        ),
        expected_output="Per-symbol technical read across all four dimensions.",
        agent=agents["technical"],
        context=[t_data],
    )
    t_quant = Task(
        description=(
            f"Call evaluate_rule_engine with student_id='{sid}' and symbols='{sym_csv}'. "
            "That composite is the reference decision. Compare it against the "
            "statistics features (z-score, 5/20/60-day trailing returns, skew) and "
            "name every symbol where you would deviate from the reference, with the "
            "number that justifies the deviation."
        ),
        expected_output="Reference composite per symbol plus an explicit list of disagreements.",
        agent=agents["quant"],
        context=[t_tech],
    )
    t_news = Task(
        description=(
            f"Call get_news_sentiment with student_id='{sid}' and symbols='{sym_csv}'. "
            "Report the sentiment label and article count per symbol. For any symbol "
            "flagged NO_NEWS_DATA say exactly that — do not supply a headline from "
            "memory or imagination."
        ),
        expected_output="Per-symbol sentiment with article counts, and explicit NO_NEWS_DATA flags.",
        agent=agents["sentiment"],
        context=[t_quant],
    )
    t_risk = Task(
        description=(
            "For every symbol you would BUY, call size_position with "
            f"student_id='{sid}', that symbol, and your conviction (LOW, MEDIUM, "
            "HIGH or VERY_HIGH). Report the notional, the ATR stop and target, and "
            "every cap that bound the size. Call get_account_snapshot and "
            f"get_positions for '{sid}' first so you know the equity and what is "
            "already held."
        ),
        expected_output="A sized candidate list with stops, targets and the caps that applied.",
        agent=agents["risk"],
        context=[t_news],
    )
    t_decide = Task(
        description=(
            "Produce the final decision for EVERY symbol analysed. Respond with "
            "STRICT JSON ONLY — no prose before or after, no markdown fence. The "
            "shape is:\n"
            '{"decisions": [{"symbol": "NVDA", "action": "BUY", '
            '"conviction": "HIGH", "composite": 0.42, "rationale": "one sentence"}]}\n'
            "action must be exactly BUY, SELL or HOLD. conviction must be exactly "
            "LOW, MEDIUM, HIGH or VERY_HIGH. Include every symbol once."
        ),
        expected_output='{"decisions": [...]} and nothing else.',
        agent=agents["decision"],
        context=[t_risk],
    )
    return [t_data, t_tech, t_quant, t_news, t_risk, t_decide]


def run_crew(
    cfg: AppConfig,
    student: StudentConfig,
    symbols: Sequence[str],
    run_logger: Optional[RunLogger] = None,
) -> CrewRunResult:
    """Run the six-agent crew.  Returns ok=False with a reason instead of raising."""
    result = CrewRunResult()
    symbols = [s.upper() for s in symbols]
    if not symbols:
        result.fallback_reason = "no symbols passed to the crew"
        return result

    # Free tiers cap tokens per minute; the crew costs roughly 2 requests per
    # symbol plus 4, so 12 symbols is about 28 requests.
    capped = symbols[: max(1, int(cfg.max_llm_symbols))]
    if len(capped) < len(symbols):
        log.warning(
            "capping the crew at %d of %d symbols (MAX_LLM_SYMBOLS); the remaining "
            "%d are decided by the deterministic rule engine",
            len(capped),
            len(symbols),
            len(symbols) - len(capped),
        )

    try:
        llm = build_crew_llm(cfg.llm)
    except LLMUnavailable as exc:
        result.fallback_reason = f"LLM unavailable: {exc}"
        result.errors.append(str(exc))
        return result

    adapter = None
    try:
        from crewai import Crew, Process

        adapter, tools = crewai_tools_from_mcp()
        if not tools:
            result.fallback_reason = "the MCP adapter exposed no tools"
            return result

        agents = build_agents(llm, tools)
        tasks = build_tasks(agents, student, capped)
        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )
        output = crew.kickoff()
        result.raw_output = str(output)

        for name, task in zip(AGENT_NAMES, tasks):
            raw = getattr(getattr(task, "output", None), "raw", "") or ""
            result.task_outputs[name] = str(raw)
            if run_logger:
                run_logger.write(
                    name,
                    summary=f"CrewAI task output for {name} (student {student.id})",
                    indicators={"symbols": capped},
                    decisions=str(raw)[:8000],
                    results="task completed",
                )

        decisions = normalise_decisions(extract_json(result.raw_output))
        if not decisions:
            # Fall back to the last task's own output before giving up.
            decisions = normalise_decisions(
                extract_json(result.task_outputs.get("Final Decision Agent", ""))
            )
        if not decisions:
            result.fallback_reason = (
                "the crew finished but produced no parseable decision JSON"
            )
            result.errors.append(result.raw_output[:800])
            return result

        result.ok = True
        result.decisions = decisions
        return result

    except MCPExtraMissing as exc:
        result.fallback_reason = f"crewai-tools[mcp] missing: {exc}"
        result.errors.append(str(exc))
        return result
    except Exception as exc:
        if is_empty_response_error(exc):
            result.fallback_reason = (
                "the model returned empty content (CrewAI: 'Invalid response from "
                "LLM call - None or empty'). Small models loop over a tool and then "
                "return nothing. Falling back to the deterministic rule engine."
            )
        else:
            result.fallback_reason = f"crew failed: {type(exc).__name__}: {exc}"
        result.errors.append(f"{type(exc).__name__}: {exc}")
        log.warning("crew run failed: %s", result.fallback_reason)
        return result
    finally:
        if adapter is not None:
            try:
                adapter.stop()
            except Exception:  # pragma: no cover
                log.debug("MCP adapter stop failed", exc_info=True)
