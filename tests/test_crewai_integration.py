"""Integration tests against a LOCAL mock OpenAI-compatible endpoint.

These exist because the brief says to check the exact payload rather than
assume it.  A real CrewAI crew, with the real MCP tools, runs against a stub
server that records every request body verbatim.  We then assert:

  * no ``cache_breakpoint`` key reaches the provider;
  * every advertised tool is strict-mode safe (>=1 parameter, and
    ``required`` == ``properties``);
  * the OpenAI SDK is pointed at our custom base URL with max_retries >= 8.

No network access is needed and no API key is used.
"""

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("crewai", reason="crewai is not installed")

from trading_system.config import LLMConfig, load_config  # noqa: E402
from trading_system.llm import build_crew_llm  # noqa: E402

CAPTURED: list[dict] = []

FINAL_JSON = json.dumps(
    {
        "decisions": [
            {"symbol": "NVDA", "action": "BUY", "conviction": "HIGH",
             "composite": 0.42, "rationale": "mock"},
            {"symbol": "TSLA", "action": "HOLD", "conviction": "LOW",
             "composite": 0.01, "rationale": "mock"},
        ]
    }
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._reply({"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
        else:
            self._reply({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode()
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"_unparsed": raw}
        CAPTURED.append({"path": self.path, "headers": dict(self.headers), "body": body})
        self._reply(
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": FINAL_JSON},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_provider():
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()


@pytest.fixture
def crew_env(monkeypatch, mock_provider, config_path, tmp_path):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", mock_provider)
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "mock-key")
    monkeypatch.setenv("LLM_MODEL", "mock-model")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MAX_LLM_SYMBOLS", "2")
    monkeypatch.setenv("CONFIG_PATH", config_path)
    monkeypatch.setenv("MODEL_RUN_DIR", str(tmp_path / "model-run"))
    monkeypatch.setenv("TRADING_LOG_DIR", str(tmp_path / "trading-logs"))
    CAPTURED.clear()
    return load_config(config_path)


class TestLLMConstruction:
    def test_the_sdk_client_points_at_our_base_url(self, mock_provider):
        llm = build_crew_llm(
            LLMConfig(provider="openai_compatible", model="mock-model",
                      base_url=mock_provider, api_key="mock-key")
        )
        client = getattr(llm, "client", None) or getattr(llm, "_client")
        assert str(client.base_url).rstrip("/") == mock_provider.rstrip("/")

    def test_max_retries_is_at_least_eight_on_the_sdk_client(self, mock_provider):
        llm = build_crew_llm(
            LLMConfig(provider="openai_compatible", model="mock-model",
                      base_url=mock_provider, api_key="k", max_retries=8)
        )
        client = getattr(llm, "client", None) or getattr(llm, "_client")
        assert client.max_retries >= 8

    def test_the_native_openai_path_is_used_not_litellm(self, mock_provider):
        """The LiteLLM fallback is what leaks cache_breakpoint."""
        llm = build_crew_llm(
            LLMConfig(provider="openai_compatible", model="mock-model",
                      base_url=mock_provider, api_key="k")
        )
        assert type(llm).__name__ == "OpenAICompletion"
        assert getattr(llm, "custom_openai", False) is True

    def test_groq_never_uses_the_litellm_prefix(self):
        from trading_system.config import resolve_llm

        os.environ["LLM_PROVIDER"] = "groq"
        os.environ["GROQ_API_KEY"] = "gsk-x"
        try:
            llm = resolve_llm({})
            assert llm.base_url.startswith("https://api.groq.com/openai/v1")
            assert not llm.model.startswith("groq/")
        finally:
            os.environ.pop("LLM_PROVIDER", None)
            os.environ.pop("GROQ_API_KEY", None)


@pytest.mark.slow
class TestRealCrewAgainstTheMockProvider:
    def test_the_crew_runs_and_its_decisions_win(self, crew_env):
        from trading_system.pipeline import CREW_ENGINE, run_for_student

        result = run_for_student(
            crew_env, "student_1", symbols=["NVDA", "TSLA"], use_llm=True
        )
        assert result.engine == CREW_ENGINE, result.fallbacks
        assert CAPTURED, "no requests reached the provider"
        actions = {s["symbol"]: s["action"] for s in result.signals}
        assert actions["NVDA"] == "BUY" and actions["TSLA"] == "HOLD"

    def test_no_cache_breakpoint_reaches_the_provider(self, crew_env):
        """crewai defines strip_cache_breakpoint() but never calls it.

        Reaching the provider through the native OpenAI path means the key is
        never built into the payload in the first place.
        """
        from trading_system.pipeline import run_for_student

        run_for_student(crew_env, "student_1", symbols=["NVDA"], use_llm=True)
        assert CAPTURED
        for record in CAPTURED:
            assert "cache_breakpoint" not in json.dumps(record["body"])
            for message in record["body"].get("messages", []):
                assert set(message) <= {
                    "role", "content", "name", "tool_calls", "tool_call_id", "refusal",
                }, f"unexpected message keys: {sorted(message)}"

    def test_every_advertised_tool_is_strict_mode_safe(self, crew_env):
        from trading_system.pipeline import run_for_student

        run_for_student(crew_env, "student_1", symbols=["NVDA"], use_llm=True)
        tool_payloads = [r["body"].get("tools") for r in CAPTURED if r["body"].get("tools")]
        assert tool_payloads, "the crew advertised no tools"
        for tools in tool_payloads:
            for tool in tools:
                fn = tool["function"]
                params = fn.get("parameters") or {}
                props = set((params.get("properties") or {}).keys())
                required = set(params.get("required") or [])
                assert props, f"{fn['name']} was advertised with zero parameters"
                assert props == required, (
                    f"{fn['name']}: strict mode forces every property into "
                    f"required; properties={sorted(props)} required={sorted(required)}"
                )

    def test_strict_mode_is_actually_on(self, crew_env):
        """If this ever turns off, the two rules above stop being load-bearing
        and the test should be revisited rather than silently passing."""
        from trading_system.pipeline import run_for_student

        run_for_student(crew_env, "student_1", symbols=["NVDA"], use_llm=True)
        tools = next(r["body"]["tools"] for r in CAPTURED if r["body"].get("tools"))
        assert any(t["function"].get("strict") for t in tools)

    def test_the_api_key_is_sent_without_whitespace(self, crew_env):
        from trading_system.pipeline import run_for_student

        run_for_student(crew_env, "student_1", symbols=["NVDA"], use_llm=True)
        auth = CAPTURED[0]["headers"].get("Authorization", "")
        assert auth == "Bearer mock-key"
        assert auth == auth.strip()
