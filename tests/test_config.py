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


class TestYamlBooleanTickerTrap:
    """PyYAML follows YAML 1.1, where a bare ON parses as the boolean True.

    ON Semiconductor is in student_3's high-beta sleeve. Unquoted, it became
    the string "TRUE" and the system submitted an order for a ticker that does
    not exist — caught in a live run on 2026-10-17.
    """

    def test_on_survives_as_a_string(self, config_path):
        cfg = load_config(config_path)
        symbols = cfg.student("student_3").symbols
        assert "ON" in symbols, symbols
        assert "TRUE" not in symbols

    def test_on_keeps_its_sector_so_the_cap_still_binds(self, config_path):
        assert load_config(config_path).sector_of("ON") == "technology"

    def test_every_ticker_in_the_file_is_quoted(self, config_path):
        """Catch the trap at its source, for any future ticker."""
        import yaml

        raw = yaml.safe_load(open(config_path, encoding="utf-8"))
        for student in raw["students"]:
            for key in ("high_beta", "diversified"):
                for ticker in student[key]:
                    assert isinstance(ticker, str), (
                        f"{student['id']}.{key} contains {ticker!r} "
                        f"({type(ticker).__name__}); quote it in the YAML"
                    )
        for key in raw["sectors"]:
            assert isinstance(key, str), f"sector key {key!r} must be quoted"

    @pytest.mark.parametrize("ticker", ["ON", "OFF", "YES", "NO", "TRUE", "FALSE"])
    def test_these_tickers_are_booleans_when_unquoted(self, ticker):
        """Documents the trap, so the list in the error message stays honest."""
        import yaml

        assert isinstance(yaml.safe_load(f"[{ticker}]")[0], bool)

    def test_clean_symbol_refuses_a_boolean(self):
        from trading_system.config import clean_symbol

        with pytest.raises(ValueError, match="parsed as a BOOLEAN"):
            clean_symbol(True, "students[student_3].high_beta")

    def test_clean_symbol_message_says_how_to_fix_it(self):
        from trading_system.config import clean_symbol

        with pytest.raises(ValueError, match="Quote it in config.yaml"):
            clean_symbol(False, "sectors")

    def test_clean_symbol_passes_ordinary_tickers_through(self):
        from trading_system.config import clean_symbol

        assert clean_symbol("  nvda\n", "x") == "NVDA"

    def test_every_symbol_is_sector_mapped(self, config_path):
        """An unmapped symbol lands in 'unknown' and escapes the sector cap."""
        assert load_config(config_path).validate_universe() == []
