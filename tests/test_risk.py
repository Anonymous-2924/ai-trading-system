"""Position sizing, exposure caps, exits-before-entries and order dedupe."""

from types import SimpleNamespace

import pytest

from trading_system.config import RiskConfig, load_config
from trading_system.risk import (
    atr_stop_and_target,
    deterministic_client_order_id,
    plan_orders,
    position_notional,
)


def sig(symbol, action, conviction="HIGH", composite=0.4, close=100.0):
    return SimpleNamespace(
        symbol=symbol, action=action, conviction=conviction,
        composite=composite, close=close,
    )


@pytest.fixture
def cfg(config_path):
    return load_config(config_path)


@pytest.fixture
def plan(cfg):
    def _plan(signals, positions=(), equity=100_000.0, cash=100_000.0,
              buying_power=None, risk=None, atr=None, prices=None):
        return plan_orders(
            student_id="student_1",
            signals=list(signals),
            positions=list(positions),
            equity=equity,
            cash=cash,
            buying_power=cash if buying_power is None else buying_power,
            risk=risk or cfg.risk,
            sector_of=cfg.sector_of,
            high_beta_symbols=cfg.student("student_1").high_beta,
            atr_by_symbol=atr or {},
            price_by_symbol=prices or {},
            day="20260101",
        )
    return _plan


class TestSizing:
    def test_conviction_scales_the_position(self, cfg):
        low = position_notional(100_000, "LOW", cfg.risk)
        med = position_notional(100_000, "MEDIUM", cfg.risk)
        high = position_notional(100_000, "HIGH", cfg.risk)
        very = position_notional(100_000, "VERY_HIGH", cfg.risk)
        assert low == 0.0, "LOW conviction must never open a position"
        assert med < high < very

    def test_single_name_cap_binds(self, cfg):
        """VERY_HIGH at 1.35x would exceed max_position_pct, so it is clipped."""
        notional = position_notional(100_000, "VERY_HIGH", cfg.risk)
        assert notional <= 100_000 * cfg.risk.max_position_pct + 1e-6

    def test_aggression_increases_the_size(self, config_path, monkeypatch):
        monkeypatch.setenv("AGGRESSION", "0.0")
        timid = load_config(config_path).risk
        monkeypatch.setenv("AGGRESSION", "1.0")
        bold = load_config(config_path).risk
        assert bold.position_pct > timid.position_pct
        assert bold.max_positions > timid.max_positions
        assert bold.max_gross_exposure > timid.max_gross_exposure
        assert bold.atr_stop_multiple > timid.atr_stop_multiple

    def test_the_default_is_aggressive_not_textbook(self, cfg):
        """The brief forbids a cautious default, so this is pinned."""
        assert cfg.aggression >= 0.6
        assert cfg.risk.position_pct > 0.05, "a 2-5% textbook size is too timid here"
        assert cfg.risk.max_gross_exposure > 1.0, "the book is expected to use margin"


class TestATRStops:
    def test_stop_and_target_are_atr_multiples(self, cfg):
        stop, target = atr_stop_and_target(100.0, 5.0, cfg.risk, "buy")
        assert stop == pytest.approx(100.0 - cfg.risk.atr_stop_multiple * 5.0)
        assert target == pytest.approx(100.0 + cfg.risk.atr_target_multiple * 5.0)

    def test_a_volatile_name_gets_a_wider_stop(self, cfg):
        calm, _ = atr_stop_and_target(100.0, 1.0, cfg.risk, "buy")
        wild, _ = atr_stop_and_target(100.0, 8.0, cfg.risk, "buy")
        assert (100.0 - wild) > (100.0 - calm)

    def test_missing_atr_falls_back_without_crashing(self, cfg):
        stop, target = atr_stop_and_target(100.0, float("nan"), cfg.risk, "buy")
        assert stop is not None and 0 < stop < 100.0 < target

    def test_stop_never_goes_negative(self, cfg):
        stop, _ = atr_stop_and_target(1.0, 50.0, cfg.risk, "buy")
        assert stop > 0


class TestLongOnly:
    def test_sell_on_an_unheld_symbol_is_no_action(self, plan):
        result = plan([sig("XOM", "SELL")])
        assert result.orders == []
        decision = next(d for d in result.decisions if d.symbol == "XOM")
        assert not decision.allowed
        assert "never" in decision.reason and "short" in decision.reason

    def test_never_emits_a_short(self, plan):
        result = plan([sig(s, "SELL") for s in ("XOM", "NVDA", "TSLA")])
        assert all(o.side == "buy" or o.qty > 0 for o in result.orders)
        assert not any(o.qty < 0 for o in result.orders)


class TestExitsBeforeEntries:
    def test_exit_proceeds_fund_entries_in_the_same_run(self, plan):
        """Cash is nearly zero; only the sale of SMCI makes the TSLA buy possible."""
        positions = [{"symbol": "SMCI", "qty": 100, "market_value": 20_000.0,
                      "current_price": 200.0}]
        result = plan(
            [sig("SMCI", "SELL"), sig("TSLA", "BUY", "VERY_HIGH", 0.7, 250.0)],
            positions=positions,
            cash=500.0,
        )
        sides = [o.side for o in result.orders]
        assert sides[0] == "sell", "the exit must be planned first"
        assert "buy" in sides, "freed capital must be recycled in the same run"
        assert any("freed capital" in n for n in result.notes)

    def test_without_the_exit_the_entry_cannot_be_afforded(self, plan):
        result = plan([sig("TSLA", "BUY", "VERY_HIGH", 0.7, 250.0)], cash=500.0)
        assert not [o for o in result.orders if o.side == "buy"]

    def test_selling_frees_the_sector_headroom_too(self, plan):
        positions = [{"symbol": "AAPL", "qty": 200, "market_value": 40_000.0,
                      "current_price": 200.0}]
        result = plan(
            [sig("AAPL", "SELL"), sig("NVDA", "BUY", "VERY_HIGH", 0.8, 100.0)],
            positions=positions,
        )
        assert any(o.symbol == "NVDA" and o.side == "buy" for o in result.orders)


class TestCaps:
    def test_max_positions_is_respected(self, plan, cfg):
        signals = [sig(f"S{i}", "BUY", "HIGH", 0.5, 10.0) for i in range(40)]
        result = plan(signals)
        assert len([o for o in result.orders if o.side == "buy"]) <= cfg.risk.max_positions

    def test_sector_cap_binds(self, plan, cfg):
        # AAPL, MSFT, NVDA, SMCI are all technology in the sample config.
        signals = [sig(s, "BUY", "VERY_HIGH", 0.8, 100.0)
                   for s in ("AAPL", "MSFT", "NVDA", "SMCI")]
        result = plan(signals)
        tech_total = sum(o.notional for o in result.orders if o.sector == "technology")
        assert tech_total <= 100_000 * cfg.risk.max_sector_pct + 1.0

    def test_gross_exposure_cap_binds(self, plan, cfg):
        signals = [sig(f"S{i}", "BUY", "VERY_HIGH", 0.9, 10.0) for i in range(30)]
        result = plan(signals, cash=1_000_000.0, buying_power=1_000_000.0)
        total = sum(o.notional for o in result.orders if o.side == "buy")
        assert total <= 100_000 * cfg.risk.max_gross_exposure + 1.0

    def test_cash_buffer_is_preserved(self, plan, cfg):
        signals = [sig(f"S{i}", "BUY", "VERY_HIGH", 0.9, 10.0) for i in range(30)]
        result = plan(signals, cash=50_000.0, buying_power=50_000.0)
        spent = sum(o.notional for o in result.orders if o.side == "buy")
        assert 50_000.0 - spent >= 100_000 * cfg.risk.min_cash_buffer_pct - 1.0

    def test_already_held_symbols_are_not_topped_up(self, plan):
        positions = [{"symbol": "NVDA", "qty": 10, "market_value": 1000.0,
                      "current_price": 100.0}]
        result = plan([sig("NVDA", "BUY", "HIGH", 0.5, 100.0)], positions=positions)
        assert not [o for o in result.orders if o.symbol == "NVDA" and o.side == "buy"]

    def test_tiny_orders_are_rejected(self, plan, cfg):
        result = plan([sig("NVDA", "BUY", "MEDIUM", 0.3, 100.0)], cash=60.0)
        assert not [o for o in result.orders if o.side == "buy"]

    def test_no_usable_price_is_rejected(self, plan):
        result = plan([sig("NVDA", "BUY", "HIGH", 0.5, float("nan"))])
        assert not result.orders
        assert any("no usable price" in d.reason for d in result.decisions)

    def test_strongest_conviction_is_funded_first(self, plan):
        signals = [
            sig("AAPL", "BUY", "MEDIUM", 0.25, 100.0),
            sig("NVDA", "BUY", "VERY_HIGH", 0.85, 100.0),
        ]
        result = plan(signals, cash=12_000.0, buying_power=12_000.0)
        assert result.orders[0].symbol == "NVDA"


class TestDedupe:
    def test_the_id_is_stable_for_the_same_intent(self):
        a = deterministic_client_order_id("student_1", "NVDA", "buy", 10.0, "20260101")
        b = deterministic_client_order_id("student_1", "NVDA", "buy", 10.0, "20260101")
        assert a == b

    def test_the_id_changes_with_every_input(self):
        base = dict(student_id="student_1", symbol="NVDA", side="buy", qty=10.0, day="20260101")
        ids = {
            deterministic_client_order_id(**base),
            deterministic_client_order_id(**{**base, "student_id": "student_2"}),
            deterministic_client_order_id(**{**base, "symbol": "TSLA"}),
            deterministic_client_order_id(**{**base, "side": "sell"}),
            deterministic_client_order_id(**{**base, "qty": 11.0}),
            deterministic_client_order_id(**{**base, "day": "20260102"}),
        }
        assert len(ids) == 6

    def test_float_noise_does_not_defeat_the_dedupe(self):
        a = deterministic_client_order_id("s1", "NVDA", "buy", 10.00001, "20260101")
        b = deterministic_client_order_id("s1", "NVDA", "buy", 10.000012, "20260101")
        assert a == b

    def test_fits_alpacas_48_character_limit(self):
        coid = deterministic_client_order_id("student_1", "GOOGL", "buy", 123.456, "20260101")
        assert len(coid) <= 48

    def test_every_planned_order_carries_an_id(self, plan):
        result = plan([sig("NVDA", "BUY", "HIGH", 0.5, 100.0)])
        assert all(o.client_order_id for o in result.orders)


class TestHighBetaSleeve:
    def test_reports_the_sleeve_percentage(self, plan):
        result = plan([sig("NVDA", "BUY", "HIGH", 0.5, 100.0)])
        assert any("high-beta sleeve" in n for n in result.notes)

    def test_flags_a_sleeve_below_the_mandate(self, plan):
        result = plan([sig("JNJ", "BUY", "HIGH", 0.5, 100.0)])
        assert any("below the" in n for n in result.notes)
