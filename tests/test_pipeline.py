"""End-to-end pipeline runs, including the announced LLM fallback."""

import json
from pathlib import Path

import pytest

from trading_system.config import load_config
from trading_system.pipeline import RULE_ENGINE, run_all, run_for_student
from trading_system.rule_engine import run_rule_engine


@pytest.fixture
def demo_cfg(monkeypatch, config_path, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("RUN_MODE", "analyse")
    monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
    monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
    monkeypatch.setenv("LLM_PROVIDER", "none")
    return load_config(config_path)


class TestDeterministicRun:
    def test_runs_without_an_llm(self, demo_cfg):
        result = run_for_student(demo_cfg, "student_1", use_llm=False)
        assert result.engine == RULE_ENGINE
        assert sum(result.counts.values()) >= 10
        assert not result.errors

    def test_is_reproducible(self, demo_cfg):
        a = run_for_student(demo_cfg, "student_1", use_llm=False)
        b = run_for_student(demo_cfg, "student_1", use_llm=False)
        actions_a = {s["symbol"]: s["action"] for s in a.signals}
        actions_b = {s["symbol"]: s["action"] for s in b.signals}
        assert actions_a == actions_b

    def test_every_student_runs(self, demo_cfg):
        results = run_all(demo_cfg, use_llm=False)
        assert len(results) == 3
        assert {r.student_id for r in results} == {"student_1", "student_2", "student_3"}

    def test_analyse_mode_submits_nothing(self, demo_cfg):
        result = run_for_student(demo_cfg, "student_1", use_llm=False)
        assert result.submitted == []
        assert any("NOT submitted" in n for n in result.notes)

    def test_demo_data_is_labelled(self, demo_cfg):
        assert run_for_student(demo_cfg, "student_1", use_llm=False).data_source == "DEMO_SYNTHETIC"


class TestArtefacts:
    def test_one_markdown_file_per_agent(self, demo_cfg):
        run_for_student(demo_cfg, "student_1", use_llm=False)
        files = sorted(Path(demo_cfg.model_run_dir).glob("*.md"))
        names = {f.name for f in files}
        assert len(files) >= 6
        for stem in ("marketDataAgent", "technicalAnalysisAgent",
                     "quantitativeAnalysisAgent", "newsSentimentAgent",
                     "riskManagementAgent", "finalDecisionAgent"):
            assert any(n.startswith(stem) for n in names), stem

    def test_filename_matches_agentNameDDMMYYYY_HH_MM(self, demo_cfg):
        import re

        run_for_student(demo_cfg, "student_1", use_llm=False)
        pattern = re.compile(r"^[a-z][A-Za-z]+\d{8}-\d{2}-\d{2}\.md$")
        for f in Path(demo_cfg.model_run_dir).glob("*.md"):
            assert pattern.match(f.name), f.name

    def test_artefacts_carry_the_experiment_configuration(self, demo_cfg):
        run_for_student(demo_cfg, "student_1", use_llm=False)
        text = next(Path(demo_cfg.model_run_dir).glob("*.md")).read_text()
        for needle in ("Experiment configuration", "aggression", "Written (UTC)",
                       "Errors"):
            assert needle in text


class TestDailyLogIntegration:
    def test_a_row_is_appended_for_the_student(self, demo_cfg):
        result = run_for_student(demo_cfg, "student_1", use_llm=False)
        assert result.log_status["ok"]
        csv_path = Path(demo_cfg.log_dir) / "student_1.csv"
        md_path = Path(demo_cfg.log_dir) / "student_1.md"
        assert csv_path.exists() and md_path.exists()

    def test_runs_accumulate_rows(self, demo_cfg):
        from trading_system.daily_log import read_rows

        for _ in range(3):
            run_for_student(demo_cfg, "student_1", use_llm=False)
        assert len(read_rows("student_1", demo_cfg.log_dir)) == 3

    def test_each_student_gets_its_own_pair_of_files(self, demo_cfg):
        run_all(demo_cfg, use_llm=False)
        for sid in ("student_1", "student_2", "student_3"):
            assert (Path(demo_cfg.log_dir) / f"{sid}.csv").exists()
            assert (Path(demo_cfg.log_dir) / f"{sid}.md").exists()


class TestFallbackIsAnnounced:
    def test_a_missing_api_key_falls_back_and_says_so(
        self, monkeypatch, config_path, tmp_path, capsys
    ):
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("LLM_PROVIDER", "ollama_cloud")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
        monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
        cfg = load_config(config_path)

        result = run_for_student(cfg, "student_1", symbols=["NVDA", "TSLA"], use_llm=True)

        assert result.engine == RULE_ENGINE
        assert result.fallbacks, "the fallback must be recorded"
        assert "FALLBACK" in capsys.readouterr().out, "the fallback must be printed"

    def test_the_fallback_reaches_the_daily_log(self, monkeypatch, config_path, tmp_path):
        from trading_system.daily_log import read_rows

        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("LLM_PROVIDER", "ollama_cloud")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
        monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
        cfg = load_config(config_path)

        run_for_student(cfg, "student_1", symbols=["NVDA"], use_llm=True)
        row = read_rows("student_1", cfg.log_dir)[-1]
        assert row["engine"] == RULE_ENGINE
        assert "LLM path unavailable" in row["notes"]

    def test_the_fallback_is_never_silent(self, monkeypatch, config_path, tmp_path):
        """Three independent channels must carry the announcement."""
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
        monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
        cfg = load_config(config_path)

        result = run_for_student(cfg, "student_1", symbols=["NVDA"], use_llm=True)
        artefacts = "\n".join(
            p.read_text() for p in Path(cfg.model_run_dir).glob("finalDecision*.md")
        )
        assert result.fallbacks                       # 1. the RunResult
        assert "FALLBACK" in artefacts                # 2. the model-run artefact
        from trading_system.daily_log import read_rows

        assert read_rows("student_1", cfg.log_dir)[-1]["engine"] == RULE_ENGINE  # 3.


class TestRefusalWithoutCredentials:
    def test_no_credentials_and_no_demo_produces_no_signals(
        self, monkeypatch, config_path, tmp_path
    ):
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("LLM_PROVIDER", "none")
        monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
        monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
        for var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                    "ALPACA_API_KEY_1", "ALPACA_SECRET_KEY_1"):
            monkeypatch.delenv(var, raising=False)
        cfg = load_config(config_path)

        result = run_for_student(cfg, "student_1", use_llm=False)
        assert result.signals == []
        assert any("never invents" in e for e in result.errors)

    def test_but_a_row_is_still_logged(self, monkeypatch, config_path, tmp_path):
        from trading_system.daily_log import read_rows

        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("LLM_PROVIDER", "none")
        monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
        monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
        for var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                    "ALPACA_API_KEY_1", "ALPACA_SECRET_KEY_1"):
            monkeypatch.delenv(var, raising=False)
        cfg = load_config(config_path)

        run_for_student(cfg, "student_1", use_llm=False)
        rows = read_rows("student_1", cfg.log_dir)
        assert len(rows) == 1 and rows[0]["data_source"] == "UNAVAILABLE"


class TestRuleEngine:
    def test_skips_symbols_with_too_little_history(self, frame_factory):
        bars = {"AAA": frame_factory(300, seed=1), "BBB": frame_factory(10, seed=2)}
        result = run_rule_engine(["AAA", "BBB"], bars)
        assert {s.symbol for s in result.signals} == {"AAA"}
        assert "BBB" in result.skipped

    def test_a_missing_symbol_is_skipped_not_fatal(self, frame_factory):
        result = run_rule_engine(["AAA", "MISSING"], {"AAA": frame_factory(300)})
        assert "MISSING" in result.skipped
        assert len(result.signals) == 1

    def test_signals_are_sorted_by_conviction(self, frame_factory):
        bars = {f"S{i}": frame_factory(300, seed=i) for i in range(6)}
        result = run_rule_engine(list(bars), bars)
        composites = [abs(s.composite) for s in result.signals]
        assert composites == sorted(composites, reverse=True)

    def test_counts_add_up(self, frame_factory):
        bars = {f"S{i}": frame_factory(300, seed=i) for i in range(6)}
        result = run_rule_engine(list(bars), bars)
        assert sum(result.counts.values()) == len(result.signals)
