"""Absolute-path entrypoint for external clients; stdout is MCP protocol only."""
from lab.mcp_server import main

if __name__ == "__main__":
    main()
