"""A LOCAL MCP server (stdio) exposing the trading toolchain.

This is OUR server, running as a subprocess over stdio.  Alpaca's hosted MCP
server is deliberately not used.

TOOL SCHEMA RULES — these are not stylistic, they are forced by CrewAI
--------------------------------------------------------------------
CrewAI advertises tools to the provider in OpenAI **strict** mode.  Two
consequences, both verified against the installed crewai
(``crewai/utilities/pydantic_schema_utils.py::ensure_all_properties_required``
and ``"strict": True`` in ``crewai/llms/providers/openai/completion.py``):

1. A tool with **zero parameters** is rejected by strict providers.  Every
   tool here therefore takes at least one argument.  A tool with nothing
   genuinely to take gets a required dummy argument named ``scope``,
   documented as "always pass 'all'".

2. Strict mode copies **every** declared property into ``required`` — including
   ones that have a Python default.  An "optional" parameter is therefore not
   expressible: the provider will demand it anyway and the model will invent a
   value.  So **no tool here has an optional parameter**.  Tuning values
   (thresholds, weights, aggression, lookbacks) come from ``config.yaml`` and
   the environment, never from a tool argument.

Every tool returns a JSON string, so nothing depends on the client's handling
of structured content.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# crewai pins mcp~=1.28, where the server class is `FastMCP`.  The mcp 2.x
# line renamed it to `MCPServer`.  Support either so the server runs under
# whichever one the environment resolved.
_SERVER_CLASS = None
_SERVER_CLASS_NAME = ""
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _SERVER_CLASS  # type: ignore

    _SERVER_CLASS_NAME = "mcp.server.fastmcp.FastMCP"
except ImportError:  # pragma: no cover - depends on the installed mcp
    try:  # mcp 2.x
        from mcp.server import MCPServer as _SERVER_CLASS  # type: ignore

        _SERVER_CLASS_NAME = "mcp.server.MCPServer"
    except ImportError:
        try:
            from mcp.server.fastmcp import MCPServer as _SERVER_CLASS  # type: ignore

            _SERVER_CLASS_NAME = "mcp.server.fastmcp.MCPServer"
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Could not import an MCP server class. Install 'mcp' "
                "(crewai pins mcp~=1.28, which provides FastMCP; mcp 2.x "
                "provides MCPServer)."
            ) from exc

if __package__ in (None, ""):  # allow `python src/trading_system/mcp_server.py`
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ""))

from trading_system.alpaca_client import (  # noqa: E402
    AlpacaClient,
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.config import AppConfig, clean, load_config  # noqa: E402
from trading_system.features import extract_features  # noqa: E402
from trading_system.paper_guard import PaperTradingViolation  # noqa: E402
from trading_system.risk import (  # noqa: E402
    deterministic_client_order_id,
    plan_orders,
    position_notional,
)
from trading_system.rule_engine import run_rule_engine  # noqa: E402
from trading_system.sentiment import analyse_batch  # noqa: E402

log = logging.getLogger("trading_system.mcp_server")

SERVER_NAME = "ai-trading-system"


class ServerContext:
    """Per-process state: config, Alpaca clients and a bars cache.

    The bars cache is what keeps the "one request for all symbols" promise
    true across tools: the agents call ``get_batched_ohlcv`` once and every
    later indicator/sentiment/rule-engine call reuses that single fetch.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config: AppConfig = load_config(config_path)
        self._clients: Dict[str, AlpacaClient] = {}
        self._bars: Dict[str, Dict[str, Any]] = {}
        self.http_requests_for_bars: Dict[str, int] = {}

    def client(self, student_id: str) -> AlpacaClient:
        sid = clean(student_id).lower()
        if sid not in self._clients:
            student = self.config.student(sid)
            self._clients[sid] = build_client(self.config, student)
        return self._clients[sid]

    def resolve_symbols(self, student_id: str, symbols: str) -> List[str]:
        """``"all"`` means the student's whole universe; otherwise a CSV list."""
        student = self.config.student(student_id)
        raw = clean(symbols)
        if not raw or raw.lower() in {"all", "*", "universe"}:
            return student.symbols
        wanted = [clean(s).upper() for s in raw.replace(";", ",").split(",") if clean(s)]
        return list(dict.fromkeys(wanted))

    def bars(self, student_id: str, symbols: List[str], refresh: bool = False):
        sid = clean(student_id).lower()
        cache = self._bars.setdefault(sid, {})
        missing = [s for s in symbols if s not in cache] if not refresh else list(symbols)
        if missing:
            client = self.client(sid)
            fetched = client.get_bars(missing, days=self.config.lookback_days)
            self.http_requests_for_bars[sid] = (
                self.http_requests_for_bars.get(sid, 0) + client.last_request_count
            )
            cache.update(fetched)
        return {s: cache[s] for s in symbols if s in cache}


CONTEXT: Optional[ServerContext] = None


def context() -> ServerContext:
    global CONTEXT
    if CONTEXT is None:
        CONTEXT = ServerContext(os.environ.get("CONFIG_PATH"))
    return CONTEXT


def _json(payload: Any) -> str:
    def default(o):
        if hasattr(o, "to_dict"):
            return o.to_dict()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

    return json.dumps(payload, default=default, indent=2, sort_keys=False)


def _error(kind: str, message: str, **extra) -> str:
    return _json({"ok": False, "error": kind, "message": message, **extra})


def _guarded(fn, *args, **kwargs) -> str:
    """Run a tool body and turn every failure into a JSON error the agent can
    read, rather than an exception that aborts the crew."""
    try:
        return fn(*args, **kwargs)
    except PaperTradingViolation as exc:
        return _error("paper_trading_violation", str(exc))
    except MarketDataUnavailable as exc:
        return _error("data_unavailable", str(exc))
    except KeyError as exc:
        return _error("unknown_student", str(exc))
    except AlpacaError as exc:
        return _error("alpaca_error", str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("tool failed")
        return _error(type(exc).__name__, str(exc))


# ---------------------------------------------------------------------------
# Tool bodies, kept importable so the tests can call them without a transport.
# ---------------------------------------------------------------------------
def _tool_get_run_configuration(scope: str) -> str:
    ctx = context()
    c = ctx.config
    return _json(
        {
            "ok": True,
            "scope": clean(scope) or "all",
            "mode": c.mode,
            "demo_mode": c.demo_mode,
            "require_human_approval": c.require_human_approval,
            "auto_execute": c.execute,
            "aggression": c.aggression,
            "max_llm_symbols": c.max_llm_symbols,
            "lookback_days": c.lookback_days,
            "alpaca_base_url": c.alpaca_base_url,
            "risk": {
                "position_pct": round(c.risk.position_pct, 4),
                "max_positions": c.risk.max_positions,
                "max_gross_exposure": round(c.risk.max_gross_exposure, 4),
                "max_position_pct": round(c.risk.max_position_pct, 4),
                "max_sector_pct": round(c.risk.max_sector_pct, 4),
                "atr_stop_multiple": round(c.risk.atr_stop_multiple, 3),
                "atr_target_multiple": round(c.risk.atr_target_multiple, 3),
                "min_high_beta_pct": c.risk.min_high_beta_pct,
            },
            "signals": c.signals,
            "students": [s.id for s in c.students],
            "note": "Tuning values live in config.yaml, never in tool arguments.",
        }
    )


def _tool_list_universe(student_id: str) -> str:
    ctx = context()
    s = ctx.config.student(student_id)
    return _json(
        {
            "ok": True,
            "student_id": s.id,
            "name": s.name,
            "symbols": s.symbols,
            "count": len(s.symbols),
            "high_beta": s.high_beta,
            "high_beta_pct": round(s.high_beta_pct, 4),
            "diversified": s.diversified,
            "sectors": {sym: ctx.config.sector_of(sym) for sym in s.symbols},
            "starting_equity": s.starting_equity,
        }
    )


def _tool_get_account_snapshot(student_id: str) -> str:
    ctx = context()
    client = ctx.client(student_id)
    acct = client.get_account()
    start = ctx.config.student(student_id).starting_equity
    equity = float(acct.get("equity") or 0.0)
    last_equity = float(acct.get("last_equity") or equity)
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "data_source": client.data_source,
            "equity": equity,
            "cash": float(acct.get("cash") or 0.0),
            "buying_power": float(acct.get("buying_power") or 0.0),
            "last_equity": last_equity,
            "day_pl": equity - last_equity,
            "day_pl_pct": ((equity / last_equity - 1.0) * 100.0) if last_equity else 0.0,
            "total_pl": equity - start,
            "total_pl_pct": ((equity / start - 1.0) * 100.0) if start else 0.0,
            "starting_equity": start,
            "status": acct.get("status"),
        }
    )


def _tool_get_positions(student_id: str) -> str:
    ctx = context()
    client = ctx.client(student_id)
    positions = client.get_positions()
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "data_source": client.data_source,
            "count": len(positions),
            "positions": positions,
            "total_market_value": round(
                sum(p["market_value"] for p in positions), 2
            ),
        }
    )


def _tool_get_batched_ohlcv(student_id: str, symbols: str) -> str:
    """ALL symbols in ONE Alpaca request.  Never one call per symbol."""
    ctx = context()
    syms = ctx.resolve_symbols(student_id, symbols)
    client = ctx.client(student_id)
    before = ctx.http_requests_for_bars.get(clean(student_id).lower(), 0)
    bars = ctx.bars(student_id, syms)
    after = ctx.http_requests_for_bars.get(clean(student_id).lower(), 0)
    summary = {}
    for sym, df in bars.items():
        summary[sym] = {
            "bars": int(len(df)),
            "first": str(df.index[0]),
            "last": str(df.index[-1]),
            "last_close": round(float(df["close"].iloc[-1]), 4),
            "last_volume": float(df["volume"].iloc[-1]),
        }
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "data_source": client.data_source,
            "requested": syms,
            "returned": sorted(bars),
            "missing": sorted(set(syms) - set(bars)),
            "http_requests_this_call": after - before,
            "batching_note": (
                "one multi-symbol request covers the whole universe; extra "
                "requests here are pagination pages, never per-symbol calls"
            ),
            "summary": summary,
            "client_notes": client.notes[-5:],
        }
    )


def _tool_compute_indicators(student_id: str, symbols: str) -> str:
    ctx = context()
    syms = ctx.resolve_symbols(student_id, symbols)
    bars = ctx.bars(student_id, syms)
    out, skipped = {}, {}
    for sym in syms:
        df = bars.get(sym)
        if df is None or len(df) < 30:
            skipped[sym] = f"insufficient history ({0 if df is None else len(df)} bars)"
            continue
        fs = extract_features(sym, df)
        out[sym] = {
            "close": fs.close,
            "as_of": fs.as_of,
            "bars_available": fs.bars_available,
            "features": {k: (None if v != v else round(v, 6)) for k, v in fs.values.items()},
            "dimensions": fs.dimension_of,
            "warnings": fs.warnings,
        }
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "feature_count": len(next(iter(out.values()))["features"]) if out else 0,
            "indicators": out,
            "skipped": skipped,
        }
    )


def _tool_get_news_sentiment(student_id: str, symbols: str) -> str:
    ctx = context()
    syms = ctx.resolve_symbols(student_id, symbols)
    client = ctx.client(student_id)
    hours = int((ctx.config.sentiment or {}).get("lookback_hours", 48))
    max_articles = int((ctx.config.sentiment or {}).get("max_articles_per_symbol", 12))
    articles = client.get_news(syms, hours=hours)
    results = analyse_batch(syms, articles, max_articles)
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "data_source": client.data_source,
            "window_hours": hours,
            "article_count": len(articles),
            "no_data_policy": (
                "headlines are never fabricated; symbols with no news score a "
                "neutral 0.0 and are flagged NO_NEWS_DATA"
            ),
            "sentiment": {k: v.to_dict() for k, v in results.items()},
        }
    )


def _tool_evaluate_rule_engine(student_id: str, symbols: str) -> str:
    ctx = context()
    syms = ctx.resolve_symbols(student_id, symbols)
    client = ctx.client(student_id)
    bars = ctx.bars(student_id, syms)
    hours = int((ctx.config.sentiment or {}).get("lookback_hours", 48))
    try:
        articles = client.get_news(syms, hours=hours)
    except MarketDataUnavailable:
        articles = []
    result = run_rule_engine(syms, bars, articles, ctx.config)
    return _json(
        {
            "ok": True,
            "student_id": clean(student_id),
            "data_source": client.data_source,
            **result.to_dict(),
        }
    )


def _tool_size_position(student_id: str, symbol: str, conviction: str) -> str:
    ctx = context()
    cfg = ctx.config
    student = cfg.student(student_id)
    client = ctx.client(student_id)
    sym = clean(symbol).upper()
    conv = clean(conviction).upper() or "MEDIUM"

    try:
        acct = client.get_account()
        equity = float(acct.get("equity") or student.starting_equity)
        cash = float(acct.get("cash") or 0.0)
        buying_power = float(acct.get("buying_power") or cash)
        positions = client.get_positions()
    except MarketDataUnavailable:
        equity, cash, buying_power, positions = (
            student.starting_equity,
            student.starting_equity,
            student.starting_equity,
            [],
        )

    bars = ctx.bars(student_id, [sym])
    price, atr = 0.0, 0.0
    if sym in bars and len(bars[sym]) >= 30:
        fs = extract_features(sym, bars[sym])
        price = fs.close
        atr = fs.values.get("atr14", 0.0)

    from types import SimpleNamespace

    signal = SimpleNamespace(
        symbol=sym, action="BUY", conviction=conv, composite=0.0, close=price
    )
    plan = plan_orders(
        student_id=student.id,
        signals=[signal],
        positions=positions,
        equity=equity,
        cash=cash,
        buying_power=buying_power,
        risk=cfg.risk,
        sector_of=cfg.sector_of,
        high_beta_symbols=student.high_beta,
        atr_by_symbol={sym: atr},
        price_by_symbol={sym: price},
    )
    return _json(
        {
            "ok": True,
            "student_id": student.id,
            "symbol": sym,
            "conviction": conv,
            "equity": equity,
            "price": price,
            "atr14": atr,
            "target_notional_before_caps": round(
                position_notional(equity, conv, cfg.risk), 2
            ),
            "plan": plan.to_dict(),
        }
    )


def _tool_place_paper_order(
    student_id: str, symbol: str, side: str, quantity: float
) -> str:
    """Submit a PAPER order.  Both paper guards run before the POST."""
    ctx = context()
    cfg = ctx.config
    student = cfg.student(student_id)
    client = ctx.client(student_id)
    sym = clean(symbol).upper()
    s = clean(side).lower()
    qty = float(quantity)

    if s not in {"buy", "sell"}:
        return _error("bad_side", f"side must be buy or sell, got {side!r}")
    if qty <= 0:
        return _error("bad_quantity", f"quantity must be positive, got {quantity!r}")

    if s == "sell":
        held = {p["symbol"] for p in client.get_positions()}
        if sym not in held:
            return _json(
                {
                    "ok": True,
                    "submitted": False,
                    "action": "no_action",
                    "reason": (
                        "long-only: a SELL on a symbol that is not held is no action, "
                        "never a short"
                    ),
                    "symbol": sym,
                }
            )

    if not cfg.execute:
        return _json(
            {
                "ok": True,
                "submitted": False,
                "action": "withheld_for_approval",
                "reason": (
                    f"mode={cfg.mode}, require_human_approval={cfg.require_human_approval}. "
                    "Orders are only submitted when mode=execute AND "
                    "REQUIRE_HUMAN_APPROVAL=false."
                ),
                "symbol": sym,
                "side": s,
                "quantity": qty,
                "client_order_id": deterministic_client_order_id(student.id, sym, s, qty),
            }
        )

    coid = deterministic_client_order_id(student.id, sym, s, qty)
    return _json({"ok": True, **client.submit_order(sym, qty, s, coid)})


def _wrap(fn):
    """Wrap a tool body in the error guard, preserving its signature.

    The registered tools call through here too, so a direct call to
    ``TOOL_BODIES[name]`` behaves exactly like the call an agent makes.
    """

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        return _guarded(fn, *args, **kwargs)

    return inner


#: Guarded tool bodies, importable so tests can exercise them without a
#: transport.  Keys match the registered tool names exactly.
TOOL_BODIES = {
    "get_run_configuration": _wrap(_tool_get_run_configuration),
    "list_universe": _wrap(_tool_list_universe),
    "get_account_snapshot": _wrap(_tool_get_account_snapshot),
    "get_positions": _wrap(_tool_get_positions),
    "get_batched_ohlcv": _wrap(_tool_get_batched_ohlcv),
    "compute_indicators": _wrap(_tool_compute_indicators),
    "get_news_sentiment": _wrap(_tool_get_news_sentiment),
    "evaluate_rule_engine": _wrap(_tool_evaluate_rule_engine),
    "size_position": _wrap(_tool_size_position),
    "place_paper_order": _wrap(_tool_place_paper_order),
}


def build_server():
    """Construct the MCP server and register every tool.

    Note the signatures: each has at least one parameter and NONE has a
    default.  See the module docstring for why.
    """
    server = _SERVER_CLASS(SERVER_NAME)

    @server.tool()
    def get_run_configuration(scope: str) -> str:
        """Return the active run configuration: mode, aggression, risk caps and
        signal thresholds.

        Args:
            scope: always pass 'all'. (This tool needs no real input, but a
                tool with zero parameters is rejected in OpenAI strict mode,
                so it takes one required dummy argument.)
        """
        return TOOL_BODIES["get_run_configuration"](scope)

    @server.tool()
    def list_universe(student_id: str) -> str:
        """List a student's tradable universe, their high-beta sleeve and each
        symbol's sector.

        Args:
            student_id: one of student_1, student_2, student_3.
        """
        return TOOL_BODIES["list_universe"](student_id)

    @server.tool()
    def get_account_snapshot(student_id: str) -> str:
        """Equity, cash, buying power and day/total P&L for one student's
        Alpaca paper account.

        Args:
            student_id: one of student_1, student_2, student_3.
        """
        return TOOL_BODIES["get_account_snapshot"](student_id)

    @server.tool()
    def get_positions(student_id: str) -> str:
        """Current open positions with market value and unrealised P&L.

        Args:
            student_id: one of student_1, student_2, student_3.
        """
        return TOOL_BODIES["get_positions"](student_id)

    @server.tool()
    def get_batched_ohlcv(student_id: str, symbols: str) -> str:
        """Fetch daily OHLCV for MANY symbols in ONE Alpaca request.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbols: comma-separated tickers, or the word 'all' for the
                student's whole universe. Always prefer 'all' — this endpoint
                is batched and one call covers every symbol.
        """
        return TOOL_BODIES["get_batched_ohlcv"](student_id, symbols)

    @server.tool()
    def compute_indicators(student_id: str, symbols: str) -> str:
        """Compute the full 29-feature technical vector (trend, momentum,
        volume, volatility, statistics) for each symbol.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbols: comma-separated tickers, or 'all' for the whole universe.
        """
        return TOOL_BODIES["compute_indicators"](student_id, symbols)

    @server.tool()
    def get_news_sentiment(student_id: str, symbols: str) -> str:
        """Score recent real news headlines per symbol. Never fabricates news:
        symbols with no headlines are reported as NO_NEWS_DATA with a neutral
        score.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbols: comma-separated tickers, or 'all' for the whole universe.
        """
        return TOOL_BODIES["get_news_sentiment"](student_id, symbols)

    @server.tool()
    def evaluate_rule_engine(student_id: str, symbols: str) -> str:
        """Run the deterministic rule engine: weighted ensemble over all
        features plus sentiment, producing BUY/SELL/HOLD with a conviction and
        a per-feature breakdown. This is the reference decision; use it as the
        baseline for your own judgement.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbols: comma-separated tickers, or 'all' for the whole universe.
        """
        return TOOL_BODIES["evaluate_rule_engine"](student_id, symbols)

    @server.tool()
    def size_position(student_id: str, symbol: str, conviction: str) -> str:
        """Risk-size one candidate entry: position notional, ATR stop-loss and
        take-profit, and every cap that applied.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbol: a single ticker, e.g. NVDA.
            conviction: one of LOW, MEDIUM, HIGH, VERY_HIGH.
        """
        return TOOL_BODIES["size_position"](student_id, symbol, conviction)

    @server.tool()
    def place_paper_order(student_id: str, symbol: str, side: str, quantity: float) -> str:
        """Submit a PAPER order to Alpaca. Paper-only: two independent guards
        validate the endpoint before the request leaves. Long-only: a sell on
        an unheld symbol is no action. Orders are withheld unless the run is
        mode=execute with REQUIRE_HUMAN_APPROVAL=false.

        Args:
            student_id: one of student_1, student_2, student_3.
            symbol: a single ticker, e.g. NVDA.
            side: 'buy' or 'sell'.
            quantity: number of shares, may be fractional. Must be positive.
        """
        return TOOL_BODIES["place_paper_order"](student_id, symbol, side, quantity)

    return server


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        stream=sys.stderr,  # stdout is the MCP transport
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info("starting MCP server using %s", _SERVER_CLASS_NAME)
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
