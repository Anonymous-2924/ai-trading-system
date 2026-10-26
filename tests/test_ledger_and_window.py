"""The trade ledger, and the clock-aware trading window.

The ledger exists because the daily log only holds totals, so it could never
answer "was NVDA a good trade" or "did VERY_HIGH beat MEDIUM".

The window logic exists because a fixed UTC cron cannot mean "30 minutes
before the close": the close moves an hour on 1 November, and GitHub's
scheduler has fired one of our runs more than three hours late.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trading_system import trade_ledger

ROOT = Path(__file__).resolve().parents[1]


def _load_window_module():
    spec = importlib.util.spec_from_file_location(
        "await_market_window", ROOT / "scripts" / "await_market_window.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


window = _load_window_module()


def make_order(symbol="NVDA", side="buy", qty=10.0, price=100.0):
    return SimpleNamespace(
        symbol=symbol, side=side, qty=qty, notional=qty * price, price=price,
        composite=0.42, conviction="HIGH", client_order_id=f"coid-{symbol}",
        stop_loss=92.0, take_profit=116.0, sector="technology", high_beta=True,
        volatility_scale=0.65, natr_pct=5.0, beta=1.7, reason="entry",
    )


class TestTradeLedger:
    def test_a_fill_captures_the_signal_that_caused_it(self):
        fill = trade_ledger.build_fill(
            student_id="student_1", order=make_order(),
            result={"submitted": True, "id": "abc", "status": "accepted", "bracket": True},
            engine="crewai_agents", run_label="morning",
        )
        assert fill.composite == pytest.approx(0.42)
        assert fill.conviction == "HIGH"
        assert fill.engine == "crewai_agents"
        assert fill.run_label == "morning"
        assert fill.volatility_scale == pytest.approx(0.65)
        assert fill.bracket is True
        assert fill.submitted is True

    def test_the_actual_fill_price_beats_the_estimate(self):
        fill = trade_ledger.build_fill(
            student_id="s1", order=make_order(price=100.0),
            result={"submitted": True, "filled_avg_price": "101.25"},
        )
        assert fill.price == pytest.approx(101.25)

    def test_without_a_fill_price_the_estimate_is_kept(self):
        fill = trade_ledger.build_fill(
            student_id="s1", order=make_order(price=100.0), result={"submitted": True}
        )
        assert fill.price == pytest.approx(100.0)

    def test_rows_accumulate_per_student(self, tmp_path):
        log_dir = str(tmp_path)
        for symbol in ("NVDA", "TSLA"):
            trade_ledger.append_fills(
                [trade_ledger.build_fill(student_id="student_2", order=make_order(symbol))],
                log_dir,
            )
        rows = trade_ledger.read_fills("student_2", log_dir)
        assert [r["symbol"] for r in rows] == ["NVDA", "TSLA"]

    def test_the_header_is_written_once(self, tmp_path):
        log_dir = str(tmp_path)
        for _ in range(3):
            trade_ledger.append_fills(
                [trade_ledger.build_fill(student_id="s1", order=make_order())], log_dir
            )
        text = (tmp_path / "trades_s1.csv").read_text()
        assert text.count("timestamp_utc") == 1

    def test_each_student_gets_their_own_file(self, tmp_path):
        trade_ledger.append_fills(
            [
                trade_ledger.build_fill(student_id="student_1", order=make_order("AAPL")),
                trade_ledger.build_fill(student_id="student_3", order=make_order("META")),
            ],
            str(tmp_path),
        )
        assert (tmp_path / "trades_student_1.csv").exists()
        assert (tmp_path / "trades_student_3.csv").exists()

    def test_an_empty_batch_is_fine(self, tmp_path):
        assert trade_ledger.append_fills([], str(tmp_path))["ok"] is True

    def test_a_ledger_failure_never_raises(self, tmp_path):
        """A logging problem must never take a trading run down with it."""
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        status = trade_ledger.append_fills(
            [trade_ledger.build_fill(student_id="s1", order=make_order())], str(blocker)
        )
        assert status["ok"] is False and status["error"]

    def test_every_column_needed_for_alpha_is_present(self):
        required = {
            "symbol", "side", "qty", "price", "composite", "conviction",
            "beta", "engine", "submitted", "date",
        }
        assert required <= set(trade_ledger.COLUMNS)


class TestDaylightSaving:
    @pytest.mark.parametrize(
        "date,daylight",
        [
            ("2026-10-26", True),    # before the switch
            ("2026-10-31", True),
            ("2026-11-01", False),   # first Sunday in November
            ("2026-11-02", False),
            ("2026-03-07", False),   # before the second Sunday in March
            ("2026-03-09", True),
            ("2026-07-01", True),
            ("2026-01-15", False),
        ],
    )
    def test_the_boundaries_are_right(self, date, daylight):
        moment = datetime.fromisoformat(date + "T12:00:00+00:00")
        assert window.is_daylight(moment) is daylight

    def test_the_offset_follows(self):
        summer = datetime.fromisoformat("2026-07-01T12:00:00+00:00")
        winter = datetime.fromisoformat("2026-12-01T12:00:00+00:00")
        assert window.eastern_offset(summer) == timedelta(hours=-4)
        assert window.eastern_offset(winter) == timedelta(hours=-5)


class FakeClient:
    def __init__(self, days):
        self._days = days

    def get_calendar(self, start, end):
        return self._days


SESSION = [{"date": "2026-10-26", "open": "09:30", "close": "16:00"}]


class TestSessionBounds:
    def test_eastern_session_maps_to_utc(self):
        now = datetime.fromisoformat("2026-10-26T14:00:00+00:00")
        opened, closed = window.session_bounds(FakeClient(SESSION), now)
        assert opened.strftime("%H:%M") == "13:30"   # 09:30 EDT
        assert closed.strftime("%H:%M") == "20:00"   # 16:00 EDT

    def test_the_same_session_shifts_an_hour_in_winter(self):
        now = datetime.fromisoformat("2026-12-01T14:00:00+00:00")
        days = [{"date": "2026-12-01", "open": "09:30", "close": "16:00"}]
        opened, closed = window.session_bounds(FakeClient(days), now)
        assert opened.strftime("%H:%M") == "14:30"   # 09:30 EST
        assert closed.strftime("%H:%M") == "21:00"   # 16:00 EST

    def test_no_session_means_no_bounds(self):
        now = datetime.now(timezone.utc)
        assert window.session_bounds(FakeClient([]), now) is None


def decide(win, now_utc, days=SESSION, max_wait=4200):
    """Mirror of the script's decision, for table-driven testing."""
    bounds = window.session_bounds(FakeClient(days), now_utc)
    if bounds is None:
        return "no-session"
    opened, closed = bounds
    if win == "open":
        target = opened + timedelta(minutes=window.OPEN_OFFSET_MINUTES)
        grace = timedelta(minutes=window.OPEN_GRACE_MINUTES)
    else:
        target = closed - timedelta(minutes=window.CLOSE_OFFSET_MINUTES)
        grace = timedelta(minutes=window.CLOSE_GRACE_MINUTES)
    if now_utc > target + grace:
        return "missed"
    if now_utc >= target:
        return "go"
    return "wait" if (target - now_utc).total_seconds() <= max_wait else "skip"


class TestWindowDecisions:
    @pytest.mark.parametrize(
        "win,utc,expected",
        [
            ("open", "2026-10-26T14:00", "wait"),    # cron fires, target 14:05
            ("open", "2026-10-26T14:05", "go"),      # exactly on target
            ("open", "2026-10-26T15:00", "go"),      # late but still usable
            ("open", "2026-10-26T17:00", "missed"),  # the 3-hour delay we saw
            ("close", "2026-10-26T19:25", "wait"),   # cron fires, target 19:30
            ("close", "2026-10-26T19:30", "go"),
            ("close", "2026-10-26T19:50", "go"),
            ("close", "2026-10-26T22:00", "missed"), # after the close
        ],
    )
    def test_decisions(self, win, utc, expected):
        assert decide(win, datetime.fromisoformat(utc + "+00:00")) == expected

    def test_the_crons_work_in_both_us_time_zones(self):
        """The whole point: one cron, correct either side of 1 November."""
        summer = [{"date": "2026-10-26", "open": "09:30", "close": "16:00"}]
        winter = [{"date": "2026-12-01", "open": "09:30", "close": "16:00"}]
        morning_cron = "T14:00:00+00:00"
        afternoon_cron = "T19:25:00+00:00"

        assert decide("open", datetime.fromisoformat("2026-10-26" + morning_cron), summer) == "wait"
        assert decide("open", datetime.fromisoformat("2026-12-01" + morning_cron), winter) == "wait"
        assert decide("close", datetime.fromisoformat("2026-10-26" + afternoon_cron), summer) == "wait"
        assert decide("close", datetime.fromisoformat("2026-12-01" + afternoon_cron), winter) == "wait"

    def test_a_weekend_is_skipped(self):
        assert decide("open", datetime.now(timezone.utc), days=[]) == "no-session"

    def test_the_morning_target_clears_the_opening_range(self):
        """The 09:30-09:45 range must have formed AND settled past the feed
        delay before ORB and RVOL mean anything."""
        assert window.OPEN_OFFSET_MINUTES >= 30

    def test_the_afternoon_target_is_inside_the_closing_hour(self):
        assert 15 <= window.CLOSE_OFFSET_MINUTES <= 60
