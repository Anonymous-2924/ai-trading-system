#!/usr/bin/env python3
"""Entry point for the local stdio MCP server.

    python scripts/run_mcp_server.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from trading_system.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
