"""Per-member daily logs: every required column, the gap row, and the mirror."""

from datetime import datetime, timedelta, timezone

import pytest

from trading_system.daily_log import (
    COLUMNS,
    append_row,
    build_row,
    read_rows,
    write_markdown,
)


@pytest.fixture
def log_dir(tmp_path):
    return str(tmp_path / "trading-logs")


def account(equity, last_equity=None):
    return {
        "equity": equity,
        "last_equity": last_equity if last_equity is not None else equity,
        "cash": equity * 0.2,
        "buying_power": equity * 1.5,
    }


class TestRequiredColumns:
    def test_every_field_the_brief_asks_for_is_present(self):
        required = {
            "timestamp_utc", "date", "equity", "cash", "buying_power",
            "day_pl", "day_pl_pct", "total_pl", "total_pl_pct",
            "open_positions", "buy_signals", "sell_signals", "hold_signals",
            "orders_submitted", "data_source",
        }
        assert required <= set(COLUMNS)

    def test_header_is_written_once(self, log_dir):
        for _ in range(3):
            append_row(build_row(student_id="student_1", starting_equity=100_000,
                                 account=account(100_000)), log_dir)
        from pathlib import Path

        text = Path(log_dir, "student_1.csv").read_text()
        assert text.count("timestamp_utc") == 1
        assert len(read_rows("student_1", log_dir)) == 3


class TestPnLArithmetic:
    def test_day_pl_is_the_move_since_the_previous_close(self, log_dir):
        row = build_row(student_id="student_1", starting_equity=100_000,
                        account=account(102_000, last_equity=100_000))
        assert row.day_pl == pytest.approx(2_000.0)
        assert row.day_pl_pct == pytest.approx(2.0)

    def test_total_pl_is_measured_against_the_100k_start(self, log_dir):
        row = build_row(student_id="student_1", starting_equity=100_000,
                        account=account(90_000, last_equity=95_000))
        assert row.total_pl == pytest.approx(-10_000.0)
        assert row.total_pl_pct == pytest.approx(-10.0)
        assert row.day_pl == pytest.approx(-5_000.0)

    def test_signal_counts_are_recorded(self):
        row = build_row(student_id="student_1", starting_equity=100_000,
                        account=account(100_000),
                        counts={"BUY": 4, "SELL": 2, "HOLD": 8})
        assert (row.buy_signals, row.sell_signals, row.hold_signals) == (4, 2, 8)


class TestGapsAreVisible:
    def test_a_run_that_cannot_read_the_account_still_appends(self, log_dir):
        status = append_row(
            build_row(student_id="student_1", starting_equity=100_000, account=None,
                      data_source="UNAVAILABLE"),
            log_dir,
        )
        assert status["ok"]
        rows = read_rows("student_1", log_dir)
        assert len(rows) == 1
        assert rows[0]["equity"] == ""
        assert rows[0]["data_source"] == "UNAVAILABLE"
        assert "gap is visible" in rows[0]["notes"]

    def test_a_logging_failure_never_raises(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        status = append_row(
            build_row(student_id="student_1", starting_equity=100_000,
                      account=account(100_000)),
            str(blocker),
        )
        assert status["ok"] is False
        assert status["error"]


class TestMarkdownMirror:
    @pytest.fixture
    def populated(self, log_dir):
        base = datetime(2026, 10, 1, 20, 5, tzinfo=timezone.utc)
        equities = [100_000, 104_000, 99_000, 107_500]
        for i, eq in enumerate(equities):
            append_row(
                build_row(
                    student_id="student_1", starting_equity=100_000,
                    account=account(eq, equities[i - 1] if i else 100_000),
                    counts={"BUY": 3, "SELL": 1, "HOLD": 9},
                    open_positions=5, orders_submitted=4,
                    data_source="ALPACA_LIVE", engine="crewai_agents",
                    mode="execute", when=base + timedelta(days=i),
                ),
                log_dir,
            )
        return log_dir

    def test_renders_a_github_table(self, populated):
        from pathlib import Path

        md = Path(populated, "student_1.md").read_text()
        assert "| --- |" in md
        assert md.count("\n|") > 6

    def test_summary_has_total_best_worst_and_up_down_days(self, populated):
        from pathlib import Path

        md = Path(populated, "student_1.md").read_text()
        for needle in ("Total P&L", "Best day", "Worst day", "Up days", "Down days",
                       "Peak equity"):
            assert needle in md

    def test_best_and_worst_days_are_right(self, populated):
        from pathlib import Path

        md = Path(populated, "student_1.md").read_text()
        # 99,000 -> 107,500 is +8.59% (the best); 104,000 -> 99,000 is
        # -4.81% (the worst).
        assert "+8.59% on 2026-10-04" in md
        assert "-4.81% on 2026-10-03" in md

    def test_total_pl_reflects_the_last_equity(self, populated):
        from pathlib import Path

        md = Path(populated, "student_1.md").read_text()
        assert "$7,500.00" in md and "+7.50%" in md

    def test_a_trailing_unreadable_row_does_not_blank_the_summary(self, populated):
        append_row(
            build_row(student_id="student_1", starting_equity=100_000, account=None),
            populated,
        )
        from pathlib import Path

        md = Path(populated, "student_1.md").read_text()
        assert "$107,500.00 (as of 2026-10-04)" in md

    def test_empty_history_is_handled(self, log_dir):
        import os

        os.makedirs(log_dir, exist_ok=True)
        path = write_markdown("student_9", log_dir)
        assert path and "No runs yet" in open(path).read()
