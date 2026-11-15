"""Local MCP read-only fixture used by the example configuration."""

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("harness-notes", log_level="WARNING")


@mcp.tool(structured_output=True)
def lookup_note(note_id: str) -> dict[str, str]:
    """读取本地试点的示例笔记，示例编号为 pilot。"""
    if note_id != "pilot":
        raise ValueError("找不到该示例笔记")
    return {"note_id": "pilot", "text": "本地 MCP 只读示例笔记。"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
