"""An actual stdio client and local HTTP server; no model or external API calls."""
import asyncio
from pathlib import Path
import socket
import sys
import threading
import time

import httpx
import uvicorn
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from lab.main import create_app
from lab.integration import TOOLS
from test_quality import draft_payload, report_payload
from test_skills import publish_test_skill


def test_real_stdio_client_roundtrip(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    app = create_app(tmp_path / "mcp.sqlite3")
    api = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=api.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not api.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert api.started
    base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base_url, trust_env=False) as http:
            payload = draft_payload(http)
            version = publish_test_skill(http)
            payload["source"]["skills"] = [{"skill_id": "dataset-design", "version_id": version["id"], "content_hash": version["content_hash"]}]
            params = StdioServerParameters(command=sys.executable,
                args=[str(Path(__file__).parents[1] / "run_mcp.py")],
                env={"LAB_API_URL": base_url, "LAB_CLIENT_NAME": "offline-protocol-test", "PYTHONIOENCODING": "utf-8"})

            async def roundtrip():
                async with Client(params, read_timeout_seconds=20) as client:
                    tools = await client.list_tools()
                    assert {t.name for t in tools.tools} == set(TOOLS)
                    assert not any("approve" in t.name or "publish" in t.name for t in tools.tools)
                    schemas = await client.call_tool("get_submission_contract")
                    assert schemas.structured_content["draft"]["properties"]["cases"]
                    catalog = await client.call_tool("list_skills", {"query": "评测集"})
                    assert catalog.structured_content["items"][0]["id"] == "dataset-design"
                    skill = await client.call_tool("get_skill", {"skill_id": "dataset-design"})
                    assert skill.structured_content["version"]["id"] == version["id"]
                    created = await client.call_tool("submit_dataset_draft", {"draft": payload})
                    assert not created.is_error, created
                    draft = created.structured_content
                    review = await client.call_tool("submit_quality_report", {"draft_id": draft["id"], "report": report_payload(draft)})
                    assert not review.is_error, review
                    saved = await client.call_tool("get_dataset_draft", {"draft_id": draft["id"]})
                    assert saved.structured_content["metrics"]["reviewed_cases"] == 1
                    missing = await client.call_tool("get_dataset_draft", {"draft_id": "missing"})
                    assert missing.is_error
                    assert missing.structured_content["error"]["code"] == "DRAFT_NOT_FOUND"
            asyncio.run(roundtrip())
            integration = http.get("/api/v1/integration").json()
            assert integration["recorded_calls"] >= 7
            assert integration["last_call"]["client"] == "offline-protocol-test"
            assert integration["last_call"]["status_code"] == 404
    finally:
        api.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
