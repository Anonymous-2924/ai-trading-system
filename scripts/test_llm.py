#!/usr/bin/env python3
"""Check in about a minute whether a model can actually drive this system.

Four stages, each with its own timeout so the whole thing stays fast:

  a) reach the provider            GET  {base_url}/models
  b) answer a plain prompt         POST {base_url}/chat/completions
  c) call an MCP tool              through the real stdio server
  d) return the structured JSON    the final task needs

A full pipeline run takes minutes; this must not.  Use it before burning a
run on a model that cannot do the job.

    python scripts/test_llm.py
    python scripts/test_llm.py --model qwen3-coder:480b --provider ollama_cloud
    python scripts/test_llm.py --list-models
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system.config import load_config  # noqa: E402
from trading_system.llm import (  # noqa: E402
    LLMUnavailable,
    list_models_hint,
    plain_completion,
    probe_provider,
)
from trading_system.mcp_client import MCPToolClient  # noqa: E402

OK, FAIL, SKIP = "PASS", "FAIL", "SKIP"

JSON_PROMPT = (
    "You are a trading decision agent. Respond with STRICT JSON only, no prose, "
    "no markdown fence. Given: NVDA composite +0.42, TSLA composite -0.31. "
    'Shape: {"decisions": [{"symbol": "...", "action": "BUY|SELL|HOLD", '
    '"conviction": "LOW|MEDIUM|HIGH|VERY_HIGH", "composite": 0.0, '
    '"rationale": "one short sentence"}]}'
)


def line(stage: str, status: str, detail: str = "", seconds: float = 0.0) -> None:
    mark = {OK: "PASS", FAIL: "FAIL", SKIP: "SKIP"}[status]
    print(f"[{mark}] {stage:<34} {seconds:5.1f}s  {detail}", flush=True)


def stage_a(cfg, timeout: int):
    t0 = time.time()
    status = probe_provider(cfg.llm, timeout=timeout)
    dt = time.time() - t0
    if not status.reachable:
        line("a) reach the provider", FAIL, status.detail, dt)
        return False, status
    if not status.authorised:
        line("a) reach the provider", FAIL, status.detail, dt)
        return False, status
    detail = status.detail
    if status.model_listed is False:
        detail += (
            f"  — NOTE: {cfg.llm.model!r} is not in the listed models. "
            "On the LOCAL Ollama daemon that is expected: cloud models end in "
            "-cloud and do not appear in /api/tags. Try it anyway."
        )
    line("a) reach the provider", OK, detail, dt)
    return True, status


def stage_b(cfg, timeout: int):
    t0 = time.time()
    try:
        reply = plain_completion(cfg.llm, "Reply with exactly: READY", timeout=timeout)
    except LLMUnavailable as exc:
        line("b) answer a plain prompt", FAIL, str(exc)[:200], time.time() - t0)
        return False
    line("b) answer a plain prompt", OK, repr(reply.strip()[:60]), time.time() - t0)
    return True


def stage_c(timeout: int):
    """Call a real MCP tool over the real stdio transport."""
    t0 = time.time()

    async def _go():
        client = MCPToolClient(extra_env={"DEMO_MODE": "true"})
        async with client.session() as c:
            tools = await c.list_tools()
            bad = [
                t["name"]
                for t in tools
                if not (t["schema"].get("properties") or {})
                or set((t["schema"].get("properties") or {}))
                != set(t["schema"].get("required") or [])
            ]
            out = await c.call("list_universe", {"student_id": "student_1"})
            return tools, bad, out

    try:
        tools, bad, out = asyncio.run(asyncio.wait_for(_go(), timeout=timeout))
    except Exception as exc:
        line("c) call an MCP tool", FAIL, f"{type(exc).__name__}: {exc}"[:200], time.time() - t0)
        return False
    dt = time.time() - t0
    if bad:
        line("c) call an MCP tool", FAIL, f"tools break strict-mode rules: {bad}", dt)
        return False
    if not isinstance(out, dict) or not out.get("ok"):
        line("c) call an MCP tool", FAIL, f"tool returned {str(out)[:120]}", dt)
        return False
    line(
        "c) call an MCP tool",
        OK,
        f"{len(tools)} tools, all strict-mode safe; list_universe -> "
        f"{out.get('count')} symbols",
        dt,
    )
    return True


def stage_d(cfg, timeout: int):
    t0 = time.time()
    try:
        reply = plain_completion(cfg.llm, JSON_PROMPT, timeout=timeout)
    except LLMUnavailable as exc:
        line("d) return structured JSON", FAIL, str(exc)[:200], time.time() - t0)
        return False
    dt = time.time() - t0

    from trading_system.agents import extract_json, normalise_decisions

    decisions = normalise_decisions(extract_json(reply))
    if not decisions:
        line(
            "d) return structured JSON",
            FAIL,
            "no parseable decisions in: " + reply.strip().replace("\n", " ")[:140],
            dt,
        )
        return False
    line("d) return structured JSON", OK, f"{len(decisions)} decision(s): {decisions}", dt)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Fast LLM capability check (~1 minute)")
    p.add_argument("--config", default=None)
    p.add_argument("--provider", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=int, default=25, help="per-stage timeout, seconds")
    p.add_argument("--list-models", action="store_true", help="print the account's models and exit")
    p.add_argument("--skip-mcp", action="store_true")
    args = p.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    cfg = load_config(args.config)
    print(
        f"provider={cfg.llm.provider}  model={cfg.llm.model}  base_url={cfg.llm.base_url}  "
        f"api_key={'set' if cfg.llm.api_key else 'MISSING'}  max_retries={cfg.llm.max_retries}"
    )
    print("-" * 100)

    if args.list_models:
        status = probe_provider(cfg.llm, timeout=args.timeout)
        if status.models:
            for m in sorted(status.models):
                print(" ", m)
        else:
            print(status.detail)
            print()
            print(list_models_hint(cfg.llm))
        return 0 if status.models else 1

    started = time.time()
    results = {}
    reachable, _ = stage_a(cfg, args.timeout)
    results["a"] = reachable
    results["b"] = stage_b(cfg, args.timeout) if reachable else False
    if not reachable:
        line("b) answer a plain prompt", SKIP, "provider unreachable")
    if args.skip_mcp:
        line("c) call an MCP tool", SKIP, "--skip-mcp")
        results["c"] = True
    else:
        results["c"] = stage_c(args.timeout)
    if results["b"]:
        results["d"] = stage_d(cfg, args.timeout)
    else:
        line("d) return structured JSON", SKIP, "no working completion endpoint")
        results["d"] = False

    print("-" * 100)
    total = time.time() - started
    passed = sum(1 for v in results.values() if v)
    print(f"{passed}/4 stages passed in {total:.1f}s")
    if not all(results.values()):
        print()
        print("This model cannot drive the crew as configured.")
        print("The deterministic rule engine still runs and produces decisions;")
        print("run the pipeline with --no-llm to use it directly.")
        print()
        print(list_models_hint(cfg.llm))
        return 1
    print("This model can drive the crew.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
