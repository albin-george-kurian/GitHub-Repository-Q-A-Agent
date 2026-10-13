"""Run the MCP server.

    python -m src.mcp_server                      # stdio, for Claude Code / Claude Desktop
    python -m src.mcp_server --transport http     # streamable HTTP on http://127.0.0.1:8765/mcp
"""

import argparse
import os
import sys
from pathlib import Path

# .env, data/indexes and data/memory.db are resolved relative to the project root, and MCP clients
# may launch this from any directory, so switch there before loading settings.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Repo Q&A MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP only. Keep 127.0.0.1 unless you add auth.")
    parser.add_argument("--port", type=int, default=8765, help="HTTP only")
    args = parser.parse_args()

    from src.mcp_server.server import mcp

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
