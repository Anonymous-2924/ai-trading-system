"""Risk management: sizing, exposure caps, stops, dedupe, buying power.

Everything here is deterministic and testable.  Key behaviours:

* **Exits before entries.** ``plan_orders`` processes SELLs first and adds the
  proceeds to the cash available to the BUYs in the same run, so freed capital
  is recycled immediately instead of waiting a day.
* **Long only.** A SELL on a symbol that is not held is NO ACTION. The system
  never opens a short.
* **Deterministic client_order_ids.** The id is a hash of
  (student, symbol, side, qty-bucket, UTC date), so re-running the same day
  cannot double-submit the same order — Alpaca rejects the duplicate id and
  the client reports it as suppressed rather than as a failure.
* **ATR stops and targets.** Both are ATR multiples, so a volatile name gets a
  proportionally wider stop instead of being stopped out by its own noise.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .config import AppConfig, RiskConfig

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"


@dataclass
class OrderPlan:
    symbol: str
    side: str                       # buy | sell
    qty: float
    notional: float
    price: float
    reason: str
    conviction: str = "MEDIUM"
    composite: float = 0.0
    client_order_id: str = ""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    sector: str = "unknown"
    high_beta: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "qty": round(self.qty, 6),
            "notional": round(self.notional, 2),
            "price": round(self.price, 4),
            "reason": self.reason,
            "conviction": self.conviction,
            "composite": round(self.composite, 4),
            "client_order_id": self.client_order_id,
            "stop_loss": round(self.stop_loss, 2) if self.stop_loss else None,
            "take_profit": round(self.take_profit, 2) if self.take_profit else None,
            "sector": self.sector,
            "high_beta": self.high_beta,
        }


@dataclass
class RiskDecision:
    """Why an order was allowed, resized or rejected."""

    symbol: str
    allowed: bool
    reason: str
    requested_notional: float = 0.0
    final_notional: float = 0.0


@dataclass
class PlanResult:
    orders: List[OrderPlan] = field(default_factory=list)
    decisions: List[RiskDecision] = field(default_factory=list)
    cash_after: float = 0.0
    gross_exposure_after: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "orders": [o.to_dict() for o in self.orders],
            "decisions": [d.__dict__ for d in self.decisions],
            "cash_after": round(self.cash_after, 2),
            "gross_exposure_after": round(self.gross_exposure_after, 4),
            "notes": self.notes,
        }


def deterministic_client_order_id(
    student_id: str, symbol: str, side: str, qty: float, day: Optional[str] = None
) -> str:
    """A stable id for (student, symbol, side, size bucket, day).

    Re-running the pipeline on the same day with the same intent produces the
    same id, so Alpaca rejects the duplicate instead of doubling the position.
    The qty is bucketed to 4 decimals so floating-point noise does not defeat
    the dedupe.
    """
    day = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    payload = f"{student_id}|{symbol.upper()}|{side.lower()}|{qty:.4f}|{day}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    # Alpaca allows up to 48 chars; keep it readable for the logs.
    return f"ats-{student_id}-{symbol.upper()}-{digest}"[:48]


def atr_stop_and_target(
    price: float, atr: float, risk: RiskConfig, side: str = "buy"
) -> tuple[Optional[float], Optional[float]]:
    """Stop loss and take profit as ATR multiples."""
    if not (price and math.isfinite(price) and price > 0):
        return None, None
    if not (atr and math.isfinite(atr) and atr > 0):
        # No ATR: fall back to percentage bands scaled the same way.
        atr = price * 0.02
    if side.lower() == "buy":
        stop = price - risk.atr_stop_multiple * atr
        target = price + risk.atr_target_multiple * atr
        return max(0.01, stop), target
    return None, None


def position_notional(
    equity: float, conviction: str, risk: RiskConfig
) -> float:
    """Base position size, scaled by conviction, capped by the single-name cap."""
    multiplier = risk.conviction_multipliers.get(conviction.upper(), 0.0)
    notional = equity * risk.position_pct * multiplier
    return min(notional, equity * risk.max_position_pct)


def plan_orders(
    *,
    student_id: str,
    signals: Sequence,
    positions: Sequence[Mapping],
    equity: float,
    cash: float,
    buying_power: float,
    risk: RiskConfig,
    sector_of,
    high_beta_symbols: Iterable[str] = (),
    atr_by_symbol: Optional[Mapping[str, float]] = None,
    price_by_symbol: Optional[Mapping[str, float]] = None,
    day: Optional[str] = None,
) -> PlanResult:
    """Turn signals into a concrete, risk-checked order list.

    ``signals`` are objects with ``symbol``, ``action``, ``conviction``,
    ``composite`` and ``close`` (a ``scoring.Signal`` satisfies this).
    """
    atr_by_symbol = dict(atr_by_symbol or {})
    price_by_symbol = dict(price_by_symbol or {})
    hb = {s.upper() for s in high_beta_symbols}
    result = PlanResult()

    held: Dict[str, dict] = {
        str(p["symbol"]).upper(): dict(p) for p in positions if p.get("symbol")
    }
    gross = sum(abs(float(p.get("market_value") or 0.0)) for p in held.values())
    sector_value: Dict[str, float] = {}
    for sym, p in held.items():
        sector_value[sector_of(sym)] = sector_value.get(sector_of(sym), 0.0) + abs(
            float(p.get("market_value") or 0.0)
        )

    available_cash = float(cash)
    buying_power = float(buying_power or cash)

    def price_for(sym: str, sig=None) -> float:
        for candidate in (
            price_by_symbol.get(sym),
            getattr(sig, "close", None) if sig is not None else None,
            held.get(sym, {}).get("current_price"),
        ):
            try:
                v = float(candidate)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0:
                return v
        return 0.0

    # ---------------------------------------------------------------
    # 1. EXITS FIRST, so the cash they free is spendable in this run.
    # ---------------------------------------------------------------
    for sig in signals:
        if sig.action != SELL:
            continue
        sym = sig.symbol.upper()
        if sym not in held:
            # Long only: a SELL on an unheld symbol is NO ACTION, never a short.
            result.decisions.append(
                RiskDecision(
                    sym,
                    False,
                    "SELL on a symbol that is not held -> no action (long-only; "
                    "this system never opens a short)",
                )
            )
            continue
        qty = abs(float(held[sym].get("qty") or 0.0))
        if qty <= 0:
            result.decisions.append(RiskDecision(sym, False, "position quantity is zero"))
            continue
        price = price_for(sym, sig)
        proceeds = qty * price
        order = OrderPlan(
            symbol=sym,
            side="sell",
            qty=qty,
            notional=proceeds,
            price=price,
            reason=f"exit: composite {sig.composite:+.3f} ({sig.conviction})",
            conviction=sig.conviction,
            composite=sig.composite,
            client_order_id=deterministic_client_order_id(student_id, sym, "sell", qty, day),
            sector=sector_of(sym),
            high_beta=sym in hb,
        )
        result.orders.append(order)
        result.decisions.append(
            RiskDecision(sym, True, "exit approved", proceeds, proceeds)
        )
        available_cash += proceeds
        buying_power += proceeds
        gross -= proceeds
        sec = sector_of(sym)
        sector_value[sec] = max(0.0, sector_value.get(sec, 0.0) - proceeds)
        held.pop(sym, None)

    if any(o.side == "sell" for o in result.orders):
        result.notes.append(
            f"exits processed first; ${sum(o.notional for o in result.orders if o.side=='sell'):,.0f} "
            "of freed capital is available to this run's entries"
        )

    # ---------------------------------------------------------------
    # 2. ENTRIES, strongest conviction first.
    # ---------------------------------------------------------------
    buys = sorted(
        [s for s in signals if s.action == BUY],
        key=lambda s: -abs(float(getattr(s, "composite", 0.0))),
    )
    open_positions = len(held)
    cash_floor = equity * risk.min_cash_buffer_pct

    for sig in buys:
        sym = sig.symbol.upper()
        price = price_for(sym, sig)
        want = position_notional(equity, sig.conviction, risk)

        if want <= 0:
            result.decisions.append(
                RiskDecision(sym, False, f"{sig.conviction} conviction does not open a position", want)
            )
            continue
        if price <= 0:
            result.decisions.append(RiskDecision(sym, False, "no usable price", want))
            continue
        if sym in held:
            result.decisions.append(
                RiskDecision(sym, False, "already held; not adding to the position", want)
            )
            continue
        if open_positions >= risk.max_positions:
            result.decisions.append(
                RiskDecision(sym, False, f"max_positions ({risk.max_positions}) reached", want)
            )
            continue

        allowed = want
        limits: List[str] = []

        headroom_gross = equity * risk.max_gross_exposure - gross
        if headroom_gross < allowed:
            limits.append(f"gross exposure cap {risk.max_gross_exposure:.2f}x")
            allowed = headroom_gross

        sec = sector_of(sym)
        headroom_sector = equity * risk.max_sector_pct - sector_value.get(sec, 0.0)
        if headroom_sector < allowed:
            limits.append(f"sector cap {risk.max_sector_pct:.0%} on {sec}")
            allowed = headroom_sector

        headroom_cash = min(available_cash - cash_floor, buying_power)
        if headroom_cash < allowed:
            limits.append("buying power / cash buffer")
            allowed = headroom_cash

        if allowed < risk.min_order_notional:
            result.decisions.append(
                RiskDecision(
                    sym,
                    False,
                    "rejected: "
                    + (", ".join(limits) if limits else "below minimum order notional")
                    + f" (room ${max(allowed, 0):,.0f} < ${risk.min_order_notional:,.0f})",
                    want,
                    max(allowed, 0.0),
                )
            )
            continue

        qty = math.floor((allowed / price) * 1000) / 1000.0  # Alpaca fractional
        if qty <= 0:
            result.decisions.append(RiskDecision(sym, False, "quantity rounds to zero", want))
            continue
        notional = qty * price
        stop, target = atr_stop_and_target(price, atr_by_symbol.get(sym, 0.0), risk, "buy")

        order = OrderPlan(
            symbol=sym,
            side="buy",
            qty=qty,
            notional=notional,
            price=price,
            reason=(
                f"entry: composite {sig.composite:+.3f} ({sig.conviction})"
                + (f"; resized by {', '.join(limits)}" if limits else "")
            ),
            conviction=sig.conviction,
            composite=sig.composite,
            client_order_id=deterministic_client_order_id(student_id, sym, "buy", qty, day),
            stop_loss=stop,
            take_profit=target,
            sector=sec,
            high_beta=sym in hb,
        )
        result.orders.append(order)
        result.decisions.append(RiskDecision(sym, True, "entry approved", want, notional))

        available_cash -= notional
        buying_power -= notional
        gross += notional
        sector_value[sec] = sector_value.get(sec, 0.0) + notional
        open_positions += 1

    # ---------------------------------------------------------------
    # 3. High-beta sleeve check (reported, not enforced by blocking).
    # ---------------------------------------------------------------
    buy_total = sum(o.notional for o in result.orders if o.side == "buy")
    if buy_total > 0:
        hb_total = sum(o.notional for o in result.orders if o.side == "buy" and o.high_beta)
        pct = hb_total / buy_total
        if pct < risk.min_high_beta_pct:
            result.notes.append(
                f"high-beta sleeve is {pct:.0%} of this run's entries, below the "
                f"{risk.min_high_beta_pct:.0%} mandate — the signal engine did not "
                "produce enough high-beta BUYs today; the mandate is measured on the "
                "whole book over the trading period, not on a single run"
            )
        else:
            result.notes.append(f"high-beta sleeve is {pct:.0%} of this run's entries")

    result.cash_after = available_cash
    result.gross_exposure_after = gross / equity if equity else 0.0
    return result
