"""Launch the Repo Q&A MCP server from any working directory (MCP clients often don't set one).

    python scripts/mcp_server.py                   # stdio, for Claude Code / Claude Desktop
    python scripts/mcp_server.py --transport http  # streamable HTTP on http://127.0.0.1:8765/mcp
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcp_server.__main__ import main  # noqa: E402  (path must be set first)

if __name__ == "__main__":
    main()
