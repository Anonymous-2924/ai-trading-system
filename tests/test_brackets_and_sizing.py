"""Bracket orders and volatility-adjusted sizing.

Two gaps found by reading our own behaviour rather than by a test failing:

* The ATR stop and take-profit were computed, logged and shown in the
  dashboard, but never sent to Alpaca. The only real exit was the next
  scheduled run noticing the score had fallen — so an overnight gap had
  nothing standing in its way.
* Every position was the same percentage of equity whether it was PG or
  MARA, so the jumpiest names quietly dominated portfolio risk.
"""

import dataclasses
import json
from types import SimpleNamespace

import pytest

from trading_system.alpaca_client import AlpacaClient
from trading_system.config import load_config
from trading_system.risk import plan_orders, position_notional, volatility_scale


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.headers = payload, status, {}
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self):
        self.bodies = []

    def request(self, method, url, **kwargs):
        self.bodies.append(kwargs.get("json"))
        return FakeResponse({"id": "order-1", "status": "accepted", "filled_qty": "0"})


@pytest.fixture
def risk(config_path):
    return load_config(config_path).risk


class TestBracketOrders:
    def test_a_plain_order_carries_no_bracket(self):
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.submit_order("AAPL", 10, "buy", "coid-1")
        assert "order_class" not in session.bodies[-1]

    def test_a_stop_and_target_become_a_bracket(self):
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        out = client.submit_order(
            "NVDA", 12, "buy", "coid-2", stop_loss=180.1234, take_profit=240.5678
        )
        body = session.bodies[-1]
        assert body["order_class"] == "bracket"
        assert body["stop_loss"] == {"stop_price": "180.12"}
        assert body["take_profit"] == {"limit_price": "240.57"}
        assert out["bracket"] is True

    def test_a_stop_alone_is_not_enough(self):
        """Alpaca needs both legs; half a bracket is not a bracket."""
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.submit_order("NVDA", 12, "buy", "coid-3", stop_loss=180.0)
        assert "order_class" not in session.bodies[-1]

    def test_fractional_quantities_are_rounded_down_for_brackets(self):
        """Alpaca rejects fractional bracket orders. Rounding DOWN keeps us
        inside the sizing limits rather than drifting over them."""
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.submit_order("NVDA", 12.74, "buy", "coid-4", stop_loss=180.0, take_profit=240.0)
        assert session.bodies[-1]["qty"] == "12.0"

    def test_a_position_too_small_to_bracket_is_skipped_not_sent_naked(self):
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        out = client.submit_order(
            "BRKA", 0.4, "buy", "coid-5", stop_loss=1.0, take_profit=2.0
        )
        assert out["submitted"] is False
        assert out["status"] == "too_small_for_bracket"
        assert session.bodies == [], "nothing should have been sent"

    def test_fractional_is_still_allowed_without_a_bracket(self):
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.submit_order("AAPL", 43.991, "buy", "coid-6")
        assert session.bodies[-1]["qty"] == "43.991"

    def test_brackets_are_enabled_by_default(self, config_path):
        assert load_config(config_path).risk.use_bracket_orders is True


class TestVolatilitySizing:
    def test_a_wild_stock_is_sized_smaller_than_a_calm_one(self, risk):
        calm = position_notional(100_000, "HIGH", risk, natr_pct=1.5)
        wild = position_notional(100_000, "HIGH", risk, natr_pct=9.0)
        assert wild < calm / 2, f"calm {calm:.0f} vs wild {wild:.0f}"

    def test_the_reference_volatility_scores_one(self, risk):
        assert volatility_scale(risk.reference_natr_pct, float("nan"), risk) == pytest.approx(1.0)

    def test_the_scale_is_clamped_at_both_ends(self, risk):
        assert volatility_scale(0.01, float("nan"), risk) == risk.max_volatility_scale
        assert volatility_scale(500.0, float("nan"), risk) == risk.min_volatility_scale

    def test_beta_is_the_fallback_when_natr_is_missing(self, risk):
        assert volatility_scale(float("nan"), 2.0, risk) == pytest.approx(0.5)

    def test_unknown_volatility_never_silently_shrinks_a_position(self, risk):
        """A missing input must not quietly size us to nothing."""
        assert volatility_scale(float("nan"), float("nan"), risk) == 1.0

    def test_sizing_can_be_turned_off(self, risk):
        off = dataclasses.replace(risk, volatility_sizing=False)
        assert volatility_scale(20.0, float("nan"), off) == 1.0

    def test_the_single_name_cap_still_binds(self, risk):
        """A very calm stock is scaled UP, but never past the hard cap."""
        notional = position_notional(100_000, "VERY_HIGH", risk, natr_pct=0.5)
        assert notional <= 100_000 * risk.max_position_pct + 1e-6

    def test_the_plan_records_the_scale_it_used(self, config_path):
        cfg = load_config(config_path)
        signal = SimpleNamespace(
            symbol="NVDA", action="BUY", conviction="HIGH", composite=0.5, close=100.0
        )
        plan = plan_orders(
            student_id="student_1", signals=[signal], positions=[],
            equity=100_000, cash=100_000, buying_power=100_000,
            risk=cfg.risk, sector_of=cfg.sector_of, high_beta_symbols=[],
            atr_by_symbol={"NVDA": 3.0}, price_by_symbol={"NVDA": 100.0},
            natr_by_symbol={"NVDA": 9.0}, day="20260101",
        )
        order = plan.orders[0]
        assert order.volatility_scale < 1.0
        assert "volatility scale" in order.reason
        assert order.to_dict()["volatility_scale"] == pytest.approx(order.volatility_scale, abs=1e-4)

    def test_the_stop_can_use_a_tighter_intraday_atr(self, config_path):
        """The playbook asks for stops off an intraday ATR, not the daily one,
        which is very wide on a high-beta name."""
        cfg = load_config(config_path)
        signal = SimpleNamespace(
            symbol="NVDA", action="BUY", conviction="HIGH", composite=0.5, close=100.0
        )
        common = dict(
            student_id="student_1", signals=[signal], positions=[],
            equity=100_000, cash=100_000, buying_power=100_000,
            risk=cfg.risk, sector_of=cfg.sector_of, high_beta_symbols=[],
            atr_by_symbol={"NVDA": 6.0}, price_by_symbol={"NVDA": 100.0},
            day="20260101",
        )
        daily_stop = plan_orders(**common).orders[0].stop_loss
        tight_stop = plan_orders(**common, stop_atr_by_symbol={"NVDA": 1.5}).orders[0].stop_loss
        assert tight_stop > daily_stop, "the intraday ATR must give a closer stop"


class TestQuotaProtection:
    def test_two_daily_crew_runs_stay_inside_the_free_tier(self, config_path):
        cfg = load_config(config_path)
        per_student = 2 * cfg.max_llm_symbols + 4
        per_day = per_student * len(cfg.students) * 2  # morning and afternoon
        assert per_day <= 100, f"{per_day} requests/day is too many for a free tier"
