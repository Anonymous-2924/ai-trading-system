"""Closing prices committed to the repository.

This exists so the dashboard can draw a stock's trajectory without asking
for Alpaca credentials. A read-only results page that demands API keys to
render a chart is a page most readers will see empty.
"""

import pandas as pd
import pytest

from trading_system import price_log


def bars(closes, start="2026-10-19"):
    index = pd.date_range(start, periods=len(closes), freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1e6] * len(closes)},
        index=index,
    )


class TestFlattening:
    def test_bars_become_one_row_per_symbol_per_day(self):
        rows = price_log.rows_from_bars({"NVDA": bars([100.0, 101.0, 102.0])})
        assert len(rows) == 3
        assert {r["symbol"] for r in rows} == {"NVDA"}
        assert rows[0]["date"] == "2026-10-19"
        assert float(rows[0]["close"]) == pytest.approx(100.0)

    def test_several_symbols_are_kept_apart(self):
        rows = price_log.rows_from_bars(
            {"NVDA": bars([100.0, 101.0]), "TSLA": bars([200.0, 202.0])})
        assert len({r["symbol"] for r in rows}) == 2

    def test_symbols_are_upper_cased(self):
        assert price_log.rows_from_bars({"nvda": bars([1.0])})[0]["symbol"] == "NVDA"

    def test_an_empty_frame_contributes_nothing(self):
        assert price_log.rows_from_bars({"NVDA": pd.DataFrame()}) == []

    def test_a_missing_frame_contributes_nothing(self):
        assert price_log.rows_from_bars({"NVDA": None}) == []

    def test_a_non_numeric_close_is_dropped_not_zeroed(self):
        frame = bars([100.0, 101.0])
        frame.loc[frame.index[1], "close"] = float("nan")
        rows = price_log.rows_from_bars({"NVDA": frame})
        assert len(rows) == 1

    def test_only_the_recent_window_is_kept(self):
        rows = price_log.rows_from_bars({"NVDA": bars([1.0] * 400)})
        assert len(rows) == price_log.MAX_DAYS

    def test_a_symbol_filter_is_honoured(self):
        rows = price_log.rows_from_bars(
            {"NVDA": bars([1.0]), "TSLA": bars([2.0])}, symbols=["nvda"])
        assert {r["symbol"] for r in rows} == {"NVDA"}


class TestWriting:
    def test_rows_round_trip(self, tmp_path):
        rows = price_log.rows_from_bars({"NVDA": bars([100.0, 101.0])})
        assert price_log.append_closes(rows, str(tmp_path))["ok"] is True
        back = price_log.read_closes(str(tmp_path))
        assert len(back) == 2

    def test_the_same_day_is_never_stored_twice(self, tmp_path):
        rows = price_log.rows_from_bars({"NVDA": bars([100.0, 101.0])})
        for _ in range(3):
            price_log.append_closes(rows, str(tmp_path))
        assert len(price_log.read_closes(str(tmp_path))) == 2

    def test_a_later_run_corrects_the_same_day(self, tmp_path):
        """The afternoon run sees a better close than the morning one."""
        price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "NVDA", "close": "100.0"}], str(tmp_path))
        price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "NVDA", "close": "104.5"}], str(tmp_path))
        rows = price_log.read_closes(str(tmp_path))
        assert len(rows) == 1
        assert float(rows[0]["close"]) == pytest.approx(104.5)

    def test_different_symbols_on_one_day_both_survive(self, tmp_path):
        price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "NVDA", "close": "100"},
             {"date": "2026-10-20", "symbol": "TSLA", "close": "200"}], str(tmp_path))
        assert len(price_log.read_closes(str(tmp_path))) == 2

    def test_the_header_is_written_once(self, tmp_path):
        for _ in range(3):
            price_log.append_closes(
                [{"date": "2026-10-20", "symbol": "NVDA", "close": "100"}], str(tmp_path))
        assert (tmp_path / price_log.FILENAME).read_text().count("date,symbol,close") == 1

    def test_the_file_cannot_grow_without_bound(self, tmp_path):
        rows = [{"date": f"2026-{m:02d}-{d:02d}", "symbol": "NVDA", "close": "100"}
                for m in range(1, 13) for d in range(1, 29)]
        price_log.append_closes(rows, str(tmp_path))
        dates = {r["date"] for r in price_log.read_closes(str(tmp_path))}
        assert len(dates) <= price_log.MAX_DAYS

    def test_an_incomplete_row_is_skipped_rather_than_written_blank(self, tmp_path):
        price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "", "close": "100"},
             {"date": "", "symbol": "NVDA", "close": "100"},
             {"date": "2026-10-20", "symbol": "NVDA", "close": "100"}], str(tmp_path))
        assert len(price_log.read_closes(str(tmp_path))) == 1

    def test_an_empty_batch_leaves_the_file_alone(self, tmp_path):
        price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "NVDA", "close": "100"}], str(tmp_path))
        price_log.append_closes([], str(tmp_path))
        assert len(price_log.read_closes(str(tmp_path))) == 1

    def test_a_write_failure_never_raises(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        status = price_log.append_closes(
            [{"date": "2026-10-20", "symbol": "NVDA", "close": "100"}], str(blocker))
        assert status["ok"] is False and status["error"]

    def test_reading_a_file_that_does_not_exist_is_empty(self, tmp_path):
        assert price_log.read_closes(str(tmp_path)) == []


class TestFramesForTheCharts:
    def test_it_returns_the_shape_the_charts_expect(self, tmp_path):
        price_log.append_closes(
            price_log.rows_from_bars(
                {"NVDA": bars([100.0, 101.0]), "TSLA": bars([200.0, 202.0])}),
            str(tmp_path))
        frames = price_log.to_frames(str(tmp_path))
        assert set(frames) == {"NVDA", "TSLA"}
        assert list(frames["NVDA"].columns) == ["close"]
        assert isinstance(frames["NVDA"].index, pd.DatetimeIndex)
        assert float(frames["NVDA"]["close"].iloc[-1]) == pytest.approx(101.0)

    def test_the_rows_come_back_in_date_order(self, tmp_path):
        price_log.append_closes(
            [{"date": "2026-10-22", "symbol": "NVDA", "close": "102"},
             {"date": "2026-10-20", "symbol": "NVDA", "close": "100"}], str(tmp_path))
        index = price_log.to_frames(str(tmp_path))["NVDA"].index
        assert list(index) == sorted(index)

    def test_no_file_means_no_frames(self, tmp_path):
        assert price_log.to_frames(str(tmp_path)) == {}


class TestDemoPricesAreNeverCommitted:
    def test_a_demo_run_writes_no_price_history(self, tmp_path):
        """Synthetic prices committed as real history would silently corrupt
        every chart and every return built on top of them."""
        from trading_system import pipeline
        from trading_system.config import load_config

        cfg = load_config("config/config.yaml")
        cfg.log_dir = str(tmp_path)
        result = pipeline.RunResult(student_id="student_1")
        result.data_source = "DEMO_SYNTHETIC"
        pipeline._record_prices(cfg, result, {"NVDA": bars([100.0, 101.0])}, {})
        assert price_log.read_closes(str(tmp_path)) == []

    def test_a_live_run_does_write_it(self, tmp_path):
        from trading_system import pipeline
        from trading_system.config import load_config

        cfg = load_config("config/config.yaml")
        cfg.log_dir = str(tmp_path)
        result = pipeline.RunResult(student_id="student_1")
        result.data_source = "ALPACA_LIVE"
        pipeline._record_prices(
            cfg, result, {"NVDA": bars([100.0, 101.0])}, {"SPY": bars([500.0, 501.0])})
        rows = price_log.read_closes(str(tmp_path))
        assert {r["symbol"] for r in rows} == {"NVDA", "SPY"}
        assert not result.errors

    def test_a_price_failure_never_breaks_the_run(self, tmp_path):
        from trading_system import pipeline
        from trading_system.config import load_config

        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory")
        cfg = load_config("config/config.yaml")
        cfg.log_dir = str(blocker)
        result = pipeline.RunResult(student_id="student_1")
        result.data_source = "ALPACA_LIVE"
        pipeline._record_prices(cfg, result, {"NVDA": bars([100.0])}, {})
        assert any("price history" in e for e in result.errors)
