"""Per-member daily logs: every required column, the gap row, and the mirror."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_system import daily_log
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


class TestTheWorkflowRebuildsEachLogWithItsOwnRenderer:
    """trading-logs/ holds three KINDS of CSV. Handing an alpha log or a trade
    ledger to the daily-log renderer does not fail -- it quietly writes a daily
    log full of "n/a" over the real file. A blanket glob did exactly that.
    """

    WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "trading-analysis.yml"

    def test_the_rebuild_dispatches_on_the_prefix(self):
        text = self.WORKFLOW.read_text()
        assert 'name.startswith("alpha_")' in text
        assert "alpha_log.write_markdown" in text

    def test_the_daily_renderer_is_not_handed_everything_it_finds(self):
        text = self.WORKFLOW.read_text()
        assert 'from trading_system.daily_log import write_markdown' not in text, (
            "the bare import was the shape of the bug: every CSV went to one renderer"
        )

    def test_the_ledger_is_left_alone(self):
        assert 'name.startswith("trades_")' in self.WORKFLOW.read_text()

    def test_an_alpha_csv_through_the_daily_renderer_is_visibly_wrong(self, tmp_path):
        """Proof the mix-up is silent, which is why the dispatch must be explicit."""
        from trading_system import alpha as alpha_lib
        from trading_system import alpha_log

        alpha_log.append_row(
            alpha_log.build_row(
                student_id="s1",
                summary=alpha_lib.Summary(trades=5, open_trades=2, mean_excess=1.5),
            ),
            str(tmp_path),
        )
        # Rendering the alpha CSV as a daily log succeeds -- and produces junk.
        daily_log.write_markdown("alpha_s1", str(tmp_path))
        text = (tmp_path / "alpha_s1.md").read_text()
        assert "daily trading log" in text.lower()
        assert "n/a" in text

    def test_the_price_history_is_not_rendered_as_a_log(self):
        """prices.csv is raw data. Through the daily-log renderer it would
        overwrite nothing useful and produce a meaningless page."""
        assert 'name == "prices"' in self.WORKFLOW.read_text()

    def test_the_price_history_is_deduplicated_after_the_merge(self):
        """The line-wise merge can leave two closes for one symbol-day."""
        assert "price_log.append_closes" in self.WORKFLOW.read_text()

    def test_the_artifacts_are_not_flattened_into_one_directory(self):
        """Every student's job uploads the WHOLE trading-logs/ directory, so
        all three artifacts hold all three CSVs -- two of them stale. Merging
        them into one directory makes the last one extracted win, which threw
        away the other students' rows. student_3's log had 2 rows against
        Shivika's 7 for exactly this reason, while every job reported success.
        """
        text = self.WORKFLOW.read_text()
        assert "merge-multiple: true" not in text
        assert "incoming/*/*.csv" in text, "the merge must walk each artifact's own directory"

    def test_the_symbol_cap_is_not_pinned_in_the_workflow(self):
        """A hard-coded fallback here silently overrode config/config.yaml, so
        lowering the quota in the config had no effect on a scheduled run."""
        text = self.WORKFLOW.read_text()
        assert "inputs.max_llm_symbols || '12'" not in text
        assert "MAX_LLM_SYMBOLS: ${{ inputs.max_llm_symbols }}" in text

    def test_an_empty_cap_falls_back_to_the_config(self):
        import os

        from trading_system.config import load_config

        previous = os.environ.get("MAX_LLM_SYMBOLS")
        os.environ["MAX_LLM_SYMBOLS"] = ""
        try:
            assert load_config("config/config.yaml").max_llm_symbols == 6
        finally:
            if previous is None:
                os.environ.pop("MAX_LLM_SYMBOLS", None)
            else:
                os.environ["MAX_LLM_SYMBOLS"] = previous

    def test_each_job_uploads_only_its_own_files(self):
        """Defence in depth. Even if a flattening download came back, two
        artifacts could no longer collide on a student's CSV."""
        text = self.WORKFLOW.read_text()
        assert "trading-logs/${{ matrix.student }}.csv" in text
        assert "trading-logs/alpha_${{ matrix.student }}.csv" in text
        assert "trading-logs/trades_${{ matrix.student }}.csv" in text

    def test_the_markdown_mirrors_are_not_shipped_in_the_artifact(self):
        """They are rebuilt from the merged CSVs; a stale copy could only
        overwrite a good one."""
        text = self.WORKFLOW.read_text()
        upload = text.split("Stash this student's daily log")[1].split("commit-logs:")[0]
        assert ".md" not in upload

    def test_every_writer_of_the_logs_shares_one_lock(self):
        """The trading run, the alpha backfill and the recovery all write
        trading-logs/. Two at once would lose rows again."""
        root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        for name in ("trading-analysis.yml", "backfill-alpha.yml", "recover-logs.yml"):
            assert "trading-logs-write" in (root / name).read_text(), name
