"""Config loading, whitespace stripping and the aggression interpolation."""

import pytest

from trading_system.config import (
    AppConfig,
    clean,
    env_bool,
    env_float,
    lerp,
    load_config,
    resolve_llm,
)


class TestWhitespaceStripping:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  sk-abc123\n", "sk-abc123"),
            ("sk-abc123\r\n", "sk-abc123"),
            ("\tsk-abc123\t", "sk-abc123"),
            ("  https://paper-api.alpaca.markets  ", "https://paper-api.alpaca.markets"),
            (None, ""),
            ("", ""),
            (12345, "12345"),
        ],
    )
    def test_clean(self, raw, expected):
        assert clean(raw) == expected

    def test_api_keys_from_the_environment_are_stripped(self, monkeypatch, config_path):
        monkeypatch.setenv("ALPACA_API_KEY_1", "  PKTESTKEY123\n")
        monkeypatch.setenv("ALPACA_SECRET_KEY_1", "secret-with-newline\n")
        cfg = load_config(config_path)
        key, secret = cfg.student("student_1").credentials()
        assert key == "PKTESTKEY123"
        assert secret == "secret-with-newline"

    def test_llm_key_is_stripped(self, monkeypatch, config_path):
        monkeypatch.setenv("OLLAMA_API_KEY", "  ollama-key\n ")
        assert load_config(config_path).llm.api_key == "ollama-key"

    def test_base_url_is_stripped(self, monkeypatch, config_path):
        monkeypatch.setenv("ALPACA_BASE_URL", " https://paper-api.alpaca.markets \n")
        assert load_config(config_path).alpaca_base_url == "https://paper-api.alpaca.markets"


class TestProviderResolution:
    def test_groq_uses_the_openai_compatible_base_url(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
        llm = resolve_llm({})
        assert llm.base_url == "https://api.groq.com/openai/v1"
        assert "groq/" not in llm.model, "never use litellm's groq/ prefix"

    def test_ollama_cloud_defaults(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama_cloud")
        monkeypatch.delenv("OLLAMA_CLOUD_BASE_URL", raising=False)
        assert resolve_llm({}).base_url == "https://ollama.com/v1"

    def test_ollama_local_needs_no_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama_local")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        llm = resolve_llm({})
        assert llm.base_url == "http://localhost:11434/v1"
        assert llm.api_key  # a placeholder, because the endpoint demands a header

    def test_unknown_provider_raises_with_the_valid_list(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "wishful")
        with pytest.raises(ValueError, match="ollama_cloud"):
            resolve_llm({})

    def test_no_model_is_hardcoded_as_the_only_option(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "some-other-model:7b")
        assert resolve_llm({}).model == "some-other-model:7b"

    def test_max_retries_is_at_least_eight(self, config_path):
        assert load_config(config_path).llm.max_retries >= 8


class TestAggression:
    def test_lerp_endpoints(self):
        assert lerp(1.0, 9.0, 0.0) == 1.0
        assert lerp(1.0, 9.0, 1.0) == 9.0
        assert lerp(1.0, 9.0, 0.5) == 5.0

    def test_lerp_clamps_out_of_range_input(self):
        assert lerp(1.0, 9.0, 5.0) == 9.0
        assert lerp(1.0, 9.0, -2.0) == 1.0

    def test_aggression_is_clamped_on_load(self, monkeypatch, config_path):
        monkeypatch.setenv("AGGRESSION", "7")
        assert load_config(config_path).aggression == 1.0
        monkeypatch.setenv("AGGRESSION", "-3")
        assert load_config(config_path).aggression == 0.0

    def test_garbage_aggression_falls_back_to_the_file(self, monkeypatch, config_path):
        monkeypatch.setenv("AGGRESSION", "banana")
        assert 0.0 <= load_config(config_path).aggression <= 1.0


class TestUniverse:
    def test_three_students_with_10_to_15_symbols_each(self, config_path):
        cfg = load_config(config_path)
        assert len(cfg.students) == 3
        for s in cfg.students:
            assert 10 <= len(s.symbols) <= 15, f"{s.id} has {len(s.symbols)}"

    def test_group_total_is_30_to_45_symbols(self, config_path):
        cfg = load_config(config_path)
        total = {sym for s in cfg.students for sym in s.symbols}
        assert 30 <= len(total) <= 45

    def test_at_least_30_percent_high_beta_each(self, config_path):
        for s in load_config(config_path).students:
            assert s.high_beta_pct >= 0.30, f"{s.id} is only {s.high_beta_pct:.1%}"

    def test_every_symbol_has_a_sector(self, config_path):
        cfg = load_config(config_path)
        for s in cfg.students:
            for sym in s.symbols:
                assert cfg.sector_of(sym) != "unknown", sym

    def test_each_student_starts_with_100k(self, config_path):
        for s in load_config(config_path).students:
            assert s.starting_equity == 100_000.0

    def test_unknown_student_raises_a_helpful_error(self, config_path):
        with pytest.raises(KeyError, match="student_1"):
            load_config(config_path).student("nobody")


class TestExecutionGate:
    def test_analyse_mode_never_auto_executes(self, monkeypatch, config_path):
        monkeypatch.setenv("RUN_MODE", "analyse")
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL", "false")
        assert load_config(config_path).execute is False

    def test_execute_with_approval_required_does_not_execute(self, monkeypatch, config_path):
        monkeypatch.setenv("RUN_MODE", "execute")
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL", "true")
        assert load_config(config_path).execute is False

    def test_both_conditions_are_needed(self, monkeypatch, config_path):
        monkeypatch.setenv("RUN_MODE", "execute")
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL", "false")
        assert load_config(config_path).execute is True

    def test_bad_mode_raises(self, monkeypatch, config_path):
        monkeypatch.setenv("RUN_MODE", "yolo")
        with pytest.raises(ValueError, match="analyse or execute"):
            load_config(config_path)

    @pytest.mark.parametrize("raw,expected",
                             [("1", True), ("TRUE", True), ("yes", True), ("on", True),
                              ("0", False), ("false", False), ("no", False), ("", None)])
    def test_env_bool(self, monkeypatch, raw, expected):
        monkeypatch.setenv("SOME_FLAG", raw)
        assert env_bool("SOME_FLAG", True) is (True if expected is None else expected)
