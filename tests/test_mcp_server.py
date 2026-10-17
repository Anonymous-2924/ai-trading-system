"""MCP server: strict-mode schema rules, tool behaviour, and a live stdio run."""

import asyncio
import json
import os

import pytest

from trading_system.mcp_server import TOOL_BODIES, build_server


@pytest.fixture(scope="module")
def tools():
    server = build_server()
    return asyncio.run(server.list_tools())


@pytest.fixture(autouse=True)
def demo_env(monkeypatch, config_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("CONFIG_PATH", config_path)
    import trading_system.mcp_server as srv

    srv.CONTEXT = None  # rebuild the context against the patched environment
    yield
    srv.CONTEXT = None


class TestStrictModeSchemaRules:
    """Both rules are forced by CrewAI advertising tools in OpenAI strict mode."""

    def test_the_expected_tools_exist(self, tools):
        names = {t.name for t in tools}
        assert names == set(TOOL_BODIES)
        for required in (
            "get_batched_ohlcv",
            "compute_indicators",
            "get_news_sentiment",
            "get_positions",
            "size_position",
            "place_paper_order",
        ):
            assert required in names

    def test_no_tool_has_zero_parameters(self, tools):
        """Strict providers reject a tool with no parameters."""
        for t in tools:
            props = (t.inputSchema or {}).get("properties") or {}
            assert props, f"{t.name} has zero parameters"

    def test_no_tool_has_an_optional_parameter(self, tools):
        """Strict mode copies EVERY property into `required`, defaults included,
        so an optional parameter is not expressible."""
        for t in tools:
            schema = t.inputSchema or {}
            props = set((schema.get("properties") or {}).keys())
            required = set(schema.get("required") or [])
            assert props == required, (
                f"{t.name}: properties {sorted(props)} != required {sorted(required)}"
            )

    def test_no_tool_signature_declares_a_default(self):
        """The rule is enforced at the source, not just in the generated schema."""
        import inspect

        server = build_server()
        for fn in TOOL_BODIES.values():
            for name, param in inspect.signature(fn).parameters.items():
                assert param.default is inspect.Parameter.empty, (
                    f"{fn.__name__} declares a default for {name!r}; "
                    "strict mode will demand it anyway"
                )

    def test_the_dummy_parameter_is_documented(self, tools):
        tool = next(t for t in tools if t.name == "get_run_configuration")
        assert "always pass 'all'" in (tool.description or "")

    def test_every_tool_is_described(self, tools):
        for t in tools:
            assert len(t.description or "") > 40, t.name


class TestToolBodies:
    def call(self, name, **kwargs):
        return json.loads(TOOL_BODIES[name](**kwargs))

    def test_list_universe(self):
        out = self.call("list_universe", student_id="student_1")
        assert out["ok"] and out["count"] >= 10
        assert out["high_beta_pct"] >= 0.30

    def test_get_run_configuration_accepts_the_dummy(self):
        out = self.call("get_run_configuration", scope="all")
        assert out["ok"] and out["mode"] in {"analyse", "execute"}
        assert "Tuning values live in config.yaml" in out["note"]

    def test_batched_ohlcv_reports_its_request_count(self):
        out = self.call("get_batched_ohlcv", student_id="student_1", symbols="all")
        assert out["ok"] and len(out["returned"]) >= 10
        assert "http_requests_this_call" in out

    def test_compute_indicators_returns_the_full_vector(self):
        out = self.call("compute_indicators", student_id="student_1", symbols="NVDA,TSLA")
        assert 20 <= out["feature_count"] <= 30
        assert set(out["indicators"]) == {"NVDA", "TSLA"}

    def test_news_sentiment_flags_the_no_data_policy(self):
        out = self.call("get_news_sentiment", student_id="student_1", symbols="NVDA")
        assert "never fabricated" in out["no_data_policy"]

    def test_evaluate_rule_engine_produces_counts(self):
        out = self.call("evaluate_rule_engine", student_id="student_1", symbols="all")
        assert set(out["counts"]) == {"BUY", "SELL", "HOLD"}
        assert sum(out["counts"].values()) >= 10

    def test_size_position_returns_a_plan(self):
        out = self.call(
            "size_position", student_id="student_1", symbol="NVDA", conviction="VERY_HIGH"
        )
        assert out["ok"] and out["target_notional_before_caps"] > 0

    def test_place_paper_order_is_withheld_in_analyse_mode(self):
        out = self.call(
            "place_paper_order",
            student_id="student_1", symbol="NVDA", side="buy", quantity=1,
        )
        assert out["submitted"] is False
        assert out["action"] == "withheld_for_approval"

    def test_sell_on_an_unheld_symbol_is_no_action(self):
        out = self.call(
            "place_paper_order",
            student_id="student_1", symbol="ZZZZ", side="sell", quantity=1,
        )
        assert out["action"] == "no_action"
        assert "never a short" in out["reason"]

    def test_bad_side_is_rejected(self):
        out = self.call(
            "place_paper_order",
            student_id="student_1", symbol="NVDA", side="short", quantity=1,
        )
        assert out["ok"] is False and out["error"] == "bad_side"

    def test_negative_quantity_is_rejected(self):
        out = self.call(
            "place_paper_order",
            student_id="student_1", symbol="NVDA", side="buy", quantity=-5,
        )
        assert out["ok"] is False and out["error"] == "bad_quantity"

    def test_an_unknown_student_returns_an_error_not_an_exception(self):
        out = self.call("list_universe", student_id="nobody")
        assert out["ok"] is False and out["error"] == "unknown_student"

    def test_symbols_all_resolves_to_the_whole_universe(self):
        a = self.call("get_batched_ohlcv", student_id="student_1", symbols="all")
        b = self.call("get_batched_ohlcv", student_id="student_1", symbols="")
        assert a["requested"] == b["requested"]


@pytest.mark.slow
class TestLiveStdioServer:
    """Actually start the server as a subprocess and talk to it."""

    def test_round_trip_over_stdio(self, config_path):
        from trading_system.mcp_client import MCPToolClient

        async def go():
            client = MCPToolClient(
                extra_env={"DEMO_MODE": "true", "CONFIG_PATH": config_path}
            )
            async with client.session() as c:
                listed = await c.list_tools()
                universe = await c.call("list_universe", {"student_id": "student_1"})
                engine = await c.call(
                    "evaluate_rule_engine",
                    {"student_id": "student_1", "symbols": "NVDA,TSLA,AAPL"},
                )
                return listed, universe, engine

        listed, universe, engine = asyncio.run(go())
        assert len(listed) == len(TOOL_BODIES)
        for t in listed:
            props = set((t["schema"].get("properties") or {}).keys())
            assert props and props == set(t["schema"].get("required") or [])
        assert universe["ok"] and universe["count"] >= 10
        assert engine["ok"] and sum(engine["counts"].values()) == 3
