"""Transport failures preserve acknowledgement uncertainty without auto-retries."""
import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location("capability_review_client", Path(__file__).parents[2] / "scripts/capability_review.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


@pytest.mark.parametrize("kind,expected", [("timeout", "状态尚未确认"), ("conflict", "STALE_REVIEW"), ("non_json", "非 JSON")])
def test_cli_does_not_retry_or_hide_submission_error(kind, expected):
    calls = []
    def handler(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("fixture", request=request)
        if kind == "conflict":
            return httpx.Response(409, json={"error": {"code": "STALE_REVIEW", "message": "refresh"}})
        return httpx.Response(500, text="Internal Server Error")
    client = cli.Client()
    client.http.close()
    client.http = httpx.Client(base_url="http://127.0.0.1:8100/api/v1", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(cli.ReviewClientError, match=expected):
            client.request("POST", "/comparisons/test/review", json={"request_id": "fixed-request"})
        assert len(calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:8100/api/v1", "http://user@localhost:8100"])
def test_cli_only_uses_local_api_roots(url):
    with pytest.raises(cli.ReviewClientError):
        cli.Client(url)


def test_mcp_timeout_has_distinct_acknowledgement_error(monkeypatch):
    import lab.mcp_server as bridge
    real_client = httpx.AsyncClient
    def handler(request):
        raise httpx.ReadTimeout("fixture", request=request)
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)))
    result = asyncio.run(bridge.call("submit_capability_review", "POST", "/comparisons/test/review", {"request_id": "same"}))
    assert result.is_error
    assert result.structured_content["error"]["code"] == "PLATFORM_TIMEOUT"


def test_mcp_non_json_response_retains_http_status(monkeypatch):
    import lab.mcp_server as bridge
    real_client = httpx.AsyncClient
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs,
        transport=httpx.MockTransport(lambda request: httpx.Response(500, text="failed"))))
    result = asyncio.run(bridge.call("submit_capability_review", "POST", "/comparisons/test/review", {}))
    assert result.is_error
    assert result.structured_content["error"]["status_code"] == 500
