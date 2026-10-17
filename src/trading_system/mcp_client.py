"""MCP client: launches the local stdio server and exposes its tools.

Two consumers:

* ``crewai_tools_from_mcp`` — hands the tools to CrewAI via
  ``MCPServerAdapter``.  That adapter lives in ``crewai-tools`` only when the
  ``[mcp]`` extra is installed: it needs ``mcpadapt``, and without it
  crewai-tools reports a confusing "missing mcp package" error even though
  ``mcp`` itself is installed.  Install ``crewai-tools[mcp]``.

* ``MCPToolClient`` — a plain async client used by the tests and by
  ``scripts/test_llm.py``, so tool calls can be verified without starting a
  whole crew.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "run_mcp_server.py"


class MCPExtraMissing(ImportError):
    """crewai-tools was installed without the [mcp] extra."""


def server_parameters(extra_env: Optional[Dict[str, str]] = None):
    """StdioServerParameters pointing at OUR local server.

    Alpaca's hosted MCP server is deliberately not used.
    """
    from mcp import StdioServerParameters  # imported lazily: mcp is optional

    env = {k: v for k, v in os.environ.items() if v is not None}
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT / "src"))
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    return StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
        env=env,
    )


@dataclass
class MCPToolClient:
    """Minimal async stdio MCP client.

    Usage::

        async with MCPToolClient().session() as c:
            tools = await c.list_tools()
            out = await c.call("list_universe", {"student_id": "student_1"})
    """

    extra_env: Dict[str, str] = field(default_factory=dict)
    _session: Any = None

    @asynccontextmanager
    async def session(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        params = server_parameters(self.extra_env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                try:
                    yield self
                finally:
                    self._session = None

    async def list_tools(self) -> List[dict]:
        resp = await self._session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "schema": t.inputSchema,
            }
            for t in resp.tools
        ]

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        result = await self._session.call_tool(name, arguments)
        chunks = []
        for item in result.content or []:
            text = getattr(item, "text", None)
            if text:
                chunks.append(text)
        payload = "\n".join(chunks)
        try:
            return json.loads(payload)
        except (ValueError, TypeError):
            return payload


def run_tool(name: str, arguments: Dict[str, Any], extra_env: Optional[Dict[str, str]] = None):
    """Synchronous one-shot: start the server, call one tool, shut down."""

    async def _go():
        client = MCPToolClient(extra_env=dict(extra_env or {}))
        async with client.session() as c:
            return await c.call(name, arguments)

    return asyncio.run(_go())


def list_tools(extra_env: Optional[Dict[str, str]] = None) -> List[dict]:
    async def _go():
        client = MCPToolClient(extra_env=dict(extra_env or {}))
        async with client.session() as c:
            return await c.list_tools()

    return asyncio.run(_go())


def crewai_tools_from_mcp(extra_env: Optional[Dict[str, str]] = None):
    """Return ``(adapter, tools)`` for CrewAI.

    The adapter owns the server subprocess and must be stopped by the caller
    (``adapter.stop()``), so agents share ONE server process and therefore one
    batched OHLCV fetch.
    """
    try:
        from crewai_tools import MCPServerAdapter  # type: ignore
    except ImportError as exc:
        raise MCPExtraMissing(
            "crewai-tools is installed without the [mcp] extra. It needs "
            "'mcpadapt'; without it crewai-tools raises a confusing "
            "'missing mcp package' error. Fix with:\n"
            "    pip install 'crewai-tools[mcp]'\n"
            "On Debian/Ubuntu, if pip fails with a PyYAML RECORD error, add "
            "--ignore-installed PyYAML."
        ) from exc

    adapter = MCPServerAdapter(server_parameters(extra_env))
    tools = adapter.tools
    log.info("MCP adapter exposed %d tools to CrewAI", len(tools))
    return adapter, tools
