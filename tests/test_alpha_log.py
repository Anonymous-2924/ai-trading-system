"""The per-member alpha log, and the backfill that fills in its history.

The alpha log exists because a single alpha number at the end of the project
says nothing about whether it was a trend or one lucky trade. One row per run
makes the measure watchable.

The backfill exists because the ledger only started recording on 2026-10-25,
while the trading started earlier. Alpaca still has those orders.
"""

import csv
import importlib.util
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from trading_system import alpha as alpha_lib
from trading_system import alpha_log, trade_ledger

ROOT = Path(__file__).resolve().parents[1]


def _load_backfill():
    spec = importlib.util.spec_from_file_location(
        "backfill_ledger", ROOT / "scripts" / "backfill_ledger.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = _load_backfill()


def summary(**kwargs):
    defaults = dict(
        trades=5, open_trades=2, mean_return=3.0, mean_excess=1.5,
        mean_jensen=0.5, total_pnl=250.0, win_rate=60.0,
        ic_return=0.2, ic_excess=0.1,
    )
    defaults.update(kwargs)
    return alpha_lib.Summary(**defaults)


def when(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class TestAlphaLog:
    def test_a_row_carries_every_measure(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(
                student_id="student_1", summary=summary(), run_label="morning",
                data_source="ALPACA_LIVE", when=when("2026-10-23T14:05:00"),
            ),
            str(tmp_path),
        )
        row = alpha_log.read_rows("student_1", str(tmp_path))[0]
        assert row["run_label"] == "morning"
        assert row["trades"] == "5"
        assert row["open_trades"] == "2"
        assert row["closed_trades"] == "3"
        assert float(row["mean_excess_pct"]) == pytest.approx(1.5)
        assert float(row["mean_jensen_pct"]) == pytest.approx(0.5)
        assert float(row["ic_return"]) == pytest.approx(0.2)
        assert row["date"] == "2026-10-23"

    def test_rows_accumulate_one_per_run(self, tmp_path):
        for label in ("morning", "afternoon", "morning"):
            alpha_log.append_row(
                alpha_log.build_row(student_id="s1", summary=summary(), run_label=label),
                str(tmp_path),
            )
        assert len(alpha_log.read_rows("s1", str(tmp_path))) == 3

    def test_the_header_is_written_once(self, tmp_path):
        for _ in range(3):
            alpha_log.append_row(
                alpha_log.build_row(student_id="s1", summary=summary()), str(tmp_path)
            )
        assert (tmp_path / "alpha_s1.csv").read_text().count("timestamp_utc") == 1

    def test_each_member_gets_their_own_file(self, tmp_path):
        for sid in ("student_1", "student_2", "student_3"):
            alpha_log.append_row(
                alpha_log.build_row(student_id=sid, summary=summary()), str(tmp_path)
            )
        for sid in ("student_1", "student_2", "student_3"):
            assert (tmp_path / f"alpha_{sid}.csv").exists()

    def test_a_missing_measure_is_blank_not_zero(self, tmp_path):
        """An unmeasurable IC must never be written as 0.000 -- that would
        read as 'the signal predicts nothing', which is a finding, not a gap."""
        alpha_log.append_row(
            alpha_log.build_row(
                student_id="s1", summary=summary(ic_return=float("nan")),
            ),
            str(tmp_path),
        )
        assert alpha_log.read_rows("s1", str(tmp_path))[0]["ic_return"] == ""

    def test_an_infinite_value_is_blank_too(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(mean_excess=float("inf"))),
            str(tmp_path),
        )
        assert alpha_log.read_rows("s1", str(tmp_path))[0]["mean_excess_pct"] == ""

    def test_a_newline_in_a_note_cannot_break_the_columns(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(), note="line one\nline two"),
            str(tmp_path),
        )
        rows = alpha_log.read_rows("s1", str(tmp_path))
        assert len(rows) == 1 and "\n" not in rows[0]["note"]

    def test_a_logging_failure_never_raises(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        status = alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary()), str(blocker)
        )
        assert status["ok"] is False and status["error"]

    def test_reading_a_log_that_does_not_exist_is_empty(self, tmp_path):
        assert alpha_log.read_rows("nobody", str(tmp_path)) == []

    def test_the_columns_never_reorder(self):
        """History stops lining up if they do."""
        assert alpha_log.COLUMNS[:4] == [
            "timestamp_utc", "date", "student_id", "run_label",
        ]


class TestAlphaMarkdown:
    def test_it_renders_the_latest_and_the_history(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(mean_excess=1.0),
                                run_label="morning", when=when("2026-10-23T14:05:00")),
            str(tmp_path))
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(mean_excess=2.5),
                                run_label="afternoon", when=when("2026-10-23T19:30:00")),
            str(tmp_path))
        text = (tmp_path / "alpha_s1.md").read_text()
        assert "## Latest" in text and "## History" in text
        assert "+2.50%" in text          # the latest reading leads
        assert "morning" in text and "afternoon" in text
        # a GitHub table needs its separator row directly under the header
        lines = [l for l in text.splitlines() if l.startswith("|")]
        assert any(set(l.replace("|", "").replace(" ", "")) <= {"-"} for l in lines)

    def test_a_small_sample_is_flagged(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(trades=4)), str(tmp_path))
        assert "Small sample" in (tmp_path / "alpha_s1.md").read_text()

    def test_a_large_sample_is_not_flagged(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(trades=40)), str(tmp_path))
        assert "Small sample" not in (tmp_path / "alpha_s1.md").read_text()

    def test_an_unmeasurable_ic_reads_as_not_available(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(ic_return=float("nan"))),
            str(tmp_path))
        text = (tmp_path / "alpha_s1.md").read_text()
        assert "| Signal IC | n/a |" in text
        assert "0.000" not in text

    def test_the_ic_row_is_a_closed_table_row_either_way(self, tmp_path):
        """Both branches of the IC row must end in a pipe, or the table breaks."""
        for ic in (0.25, float("nan")):
            alpha_log.append_row(
                alpha_log.build_row(student_id=f"s{ic}", summary=summary(ic_return=ic)),
                str(tmp_path))
            row = [l for l in (tmp_path / f"alpha_s{ic}.md").read_text().splitlines()
                   if l.startswith("| Signal IC")][0]
            assert row.rstrip().endswith("|"), row

    def test_an_empty_log_still_produces_a_page(self, tmp_path):
        assert alpha_log.write_markdown("nobody", str(tmp_path))
        assert "No trades measured yet" in (tmp_path / "alpha_nobody.md").read_text()

    def test_notes_are_surfaced(self, tmp_path):
        alpha_log.append_row(
            alpha_log.build_row(student_id="s1", summary=summary(),
                                note="backfilled, so IC is not computable"),
            str(tmp_path))
        assert "not computable" in (tmp_path / "alpha_s1.md").read_text()


class TestBackfillRows:
    def order(self, **kwargs):
        base = dict(
            id="ord-1", client_order_id="coid-1", symbol="nvda", side="buy",
            filled_qty="10", filled_avg_price="123.45", status="filled",
            submitted_at="2026-10-20T14:06:00Z", filled_at="2026-10-20T14:06:02Z",
        )
        base.update(kwargs)
        return base

    def test_a_filled_order_becomes_a_ledger_row(self):
        row = backfill.to_row("student_1", self.order())
        assert row["symbol"] == "NVDA"           # upper-cased
        assert row["side"] == "buy"
        assert float(row["qty"]) == pytest.approx(10.0)
        assert float(row["price"]) == pytest.approx(123.45)
        assert float(row["notional"]) == pytest.approx(1234.5)
        assert row["submitted"] == "True"
        assert row["date"] == "2026-10-20"

    def test_an_order_that_never_filled_is_not_a_trade(self):
        assert backfill.to_row("s1", self.order(filled_qty="0", status="canceled")) is None

    def test_a_rejected_order_is_not_a_trade(self):
        assert backfill.to_row("s1", self.order(filled_qty="0", status="rejected")) is None

    def test_the_missing_score_is_left_empty_never_guessed(self):
        """The composite score is what the IC correlates against. Inventing
        one would corrupt the single statistic the ledger exists to produce."""
        row = backfill.to_row("s1", self.order())
        assert row["composite"] == ""
        assert row["conviction"] == ""

    def test_a_backfilled_row_says_so(self):
        assert backfill.to_row("s1", self.order())["engine"] == "backfilled_from_alpaca"

    def test_every_ledger_column_is_present(self):
        assert set(backfill.to_row("s1", self.order())) == set(trade_ledger.COLUMNS)

    @pytest.mark.parametrize(
        "stamp,label",
        [
            ("2026-10-20T14:06:00Z", "morning"),    # 10:06 ET
            ("2026-10-20T19:31:00Z", "afternoon"),  # 15:31 ET
            ("2026-12-01T14:35:00Z", "morning"),    # 09:35 EST
            ("2026-12-01T20:30:00Z", "afternoon"),  # 15:30 EST
        ],
    )
    def test_the_run_is_labelled_from_eastern_time(self, stamp, label):
        assert backfill.run_label_for(stamp) == label

    def test_an_unparseable_timestamp_does_not_crash(self):
        assert backfill.run_label_for("not a date") == "backfilled"

    def test_the_limit_price_stands_in_when_there_is_no_fill_price(self):
        order = self.order(filled_avg_price=None, limit_price="99.5")
        assert backfill.fill_price(order) == pytest.approx(99.5)

    def test_a_missing_price_is_not_a_number(self):
        assert not math.isfinite(
            backfill.fill_price(self.order(filled_avg_price=None))
        )


class TestBackfillLedgerWrites:
    def test_reconstructed_rows_keep_the_column_order(self, tmp_path):
        rows = [
            {"student_id": "s1", "symbol": "NVDA", "side": "buy", "qty": "10",
             "unknown_key": "ignore me"},
        ]
        assert trade_ledger.append_rows(rows, str(tmp_path))["ok"] is True
        with (tmp_path / "trades_s1.csv").open() as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == trade_ledger.COLUMNS
            row = next(reader)
        assert row["symbol"] == "NVDA" and row["composite"] == ""
        assert "unknown_key" not in row

    def test_reconstructed_rows_append_beside_recorded_ones(self, tmp_path):
        trade_ledger.append_fills(
            [trade_ledger.build_fill(
                student_id="s1",
                order=type("O", (), dict(
                    symbol="AAPL", side="buy", qty=1.0, notional=100.0, price=100.0,
                    composite=0.4, conviction="HIGH", client_order_id="x",
                    stop_loss=None, take_profit=None, sector="tech", high_beta=False,
                    volatility_scale=1.0, natr_pct=2.0, beta=1.1, reason="entry"))(),
                result={"submitted": True})],
            str(tmp_path))
        trade_ledger.append_rows(
            [{"student_id": "s1", "symbol": "NVDA", "side": "buy", "submitted": "True"}],
            str(tmp_path))
        rows = trade_ledger.read_fills("s1", str(tmp_path))
        assert [r["symbol"] for r in rows] == ["AAPL", "NVDA"]
        assert (tmp_path / "trades_s1.csv").read_text().count("timestamp_utc") == 1

    def test_an_empty_batch_is_fine(self, tmp_path):
        assert trade_ledger.append_rows([], str(tmp_path))["ok"] is True

    def test_a_write_failure_never_raises(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory")
        status = trade_ledger.append_rows([{"student_id": "s1"}], str(blocker))
        assert status["ok"] is False and status["error"]


class TestBackfillBeta:
    def build(self, true_beta):
        index = pd.date_range("2026-01-01", periods=200, freq="B")
        import numpy as np
        rng = np.random.default_rng(11)
        market = rng.normal(0.0004, 0.009, len(index))
        own = true_beta * market + rng.normal(0, 0.0015, len(index))
        bench = pd.DataFrame({"close": 500 * np.exp(np.cumsum(market))}, index=index)
        stock = pd.DataFrame({"close": 100 * np.exp(np.cumsum(own))}, index=index)
        return stock, bench

    def test_beta_is_measured_not_assumed(self):
        """Beta was never recorded for past trades, but unlike the score it can
        be measured from prices, so it is -- the same way the live path does."""
        stock, bench = self.build(1.9)
        betas = backfill.measured_betas({"NVDA": stock}, bench, [])
        last = sorted(betas)[-1]
        assert betas[last] == pytest.approx(1.9, abs=0.15)

    def test_the_beta_used_is_the_one_as_of_the_entry_date(self):
        stock, bench = self.build(1.5)
        betas = backfill.measured_betas({"NVDA": stock}, bench, [])
        date = sorted(k.split("|")[1] for k in betas)[-5]
        assert backfill.nearest_beta(betas, "NVDA", date) == pytest.approx(
            betas[f"NVDA|{date}"])

    def test_a_date_with_no_reading_falls_back_to_the_last_one_before_it(self):
        betas = {"NVDA|2026-10-20": 1.7, "NVDA|2026-10-21": 1.8}
        assert backfill.nearest_beta(betas, "NVDA", "2026-10-25") == pytest.approx(1.8)

    def test_a_date_before_any_reading_has_no_beta(self):
        betas = {"NVDA|2026-10-20": 1.7}
        assert not math.isfinite(backfill.nearest_beta(betas, "NVDA", "2026-10-01"))

    def test_an_unknown_symbol_has_no_beta(self):
        assert not math.isfinite(backfill.nearest_beta({"NVDA|2026-10-20": 1.7}, "TSLA", "2026-10-20"))

    def test_without_a_benchmark_there_are_no_betas(self):
        stock, _ = self.build(1.5)
        assert backfill.measured_betas({"NVDA": stock}, None, []) == {}

    def test_too_little_history_is_skipped_rather_than_guessed(self):
        stock, bench = self.build(1.5)
        assert backfill.measured_betas({"NVDA": stock.head(10)}, bench, []) == {}


class TestBackfillHonesty:
    def test_the_ic_caveat_is_stated(self):
        assert "information coefficient" in backfill.IC_CAVEAT.lower()
        assert "cannot be computed" in backfill.IC_CAVEAT.lower()

    def test_an_ic_cannot_be_computed_from_backfilled_trades(self):
        """Without a score at entry there is nothing to correlate, so the IC
        must come out unmeasurable rather than as a number."""
        positions = [
            alpha_lib.Position(
                symbol=s, entry_price=100.0, exit_price=110.0, notional=1000.0,
                composite=float("nan"), still_open=False)
            for s in ("NVDA", "TSLA", "AMD", "PLTR")
        ]
        assert not math.isfinite(alpha_lib.summarise(positions).ic_return)
