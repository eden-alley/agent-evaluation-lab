import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lab.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        yield client


def project(client):
    response = client.post("/api/v1/projects", json={"name": "First"})
    assert response.status_code == 201
    return response.json()


def registration(root, **kwargs):
    return {"name": "Local agent", "source_path": str(root),
            "python_executable": str(root / "python"), "entrypoint": "agent.py", **kwargs}


def test_project_persistence_and_update(tmp_path):
    db = tmp_path / "lab.sqlite3"
    with TestClient(create_app(db)) as client:
        p = project(client)
        updated = client.patch(f"/api/v1/projects/{p['id']}", json={"description": "saved"})
        assert updated.json()["description"] == "saved"
    with TestClient(create_app(db)) as client:
        assert client.get("/api/v1/projects").json()["items"][0]["description"] == "saved"
        assert client.get(f"/api/v1/projects/{p['id']}").json()["name"] == "First"
        assert client.get("/api/v1/health").json()["journal_mode"] == "wal"
    with sqlite3.connect(db) as db_conn:
        assert db_conn.execute("pragma foreign_key_check").fetchall() == []


def test_invalid_requests_return_safe_json(client):
    for payload in ({"name": " "}, {"name": "x", "extra": 1}, {"name": 5}):
        result = client.post("/api/v1/projects", json=payload)
        assert result.status_code == 422
        assert "error" in result.json()
    assert client.patch("/api/v1/projects/missing", json={"name": "x"}).status_code == 404
    assert client.post("/api/v1/projects", content="{").status_code == 422


def test_agent_is_singleton_and_missing_is_reported(client, tmp_path):
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    assert client.get(url).json()["error"]["code"] == "AGENT_NOT_REGISTERED"
    assert client.post(url + "/check").status_code == 404
    first = client.put(url, json=registration(tmp_path)).json()
    second = client.put(url, json=registration(tmp_path, name="Updated")).json()
    assert second["id"] == first["id"]
    assert client.get(url).json()["name"] == "Updated"
    report = client.post(url + "/check").json()
    assert report["configuration_status"] == "unavailable"
    assert report["runtime_status"] == "not_tested"
    assert client.get(url).json()["last_check"] == report


def test_secret_keys_and_invalid_entrypoint_are_rejected(client, tmp_path):
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    for entry in ("../outside.py", "/tmp/outside.py", "agent.txt"):
        assert client.put(url, json=registration(tmp_path, entrypoint=entry)).status_code == 422
    result = client.put(url, json=registration(tmp_path, config={"nested": {"API_KEY": "do-not-echo"}}))
    assert result.status_code == 422
    assert "do-not-echo" not in result.text


def test_static_check_never_executes_files_and_reports_no_git(client, tmp_path):
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    marker = tmp_path / "executed"
    (tmp_path / "python").write_text(f"touch {marker}")
    (tmp_path / "agent.py").write_text(f"open({str(marker)!r}, 'w').write('executed')")
    assert client.put(url, json=registration(tmp_path)).status_code == 200
    report = client.post(url + "/check").json()
    assert report["configuration_status"] == "ready"
    assert report["runtime_status"] == "not_tested"
    assert report["git_commit"] is None and report["git_dirty"] is None
    assert not marker.exists()


def test_symlink_escape_does_not_report_ready(client, tmp_path):
    p = project(client)
    root = tmp_path / "root"
    root.mkdir()
    (root / "python").touch()
    outside = tmp_path / "outside.py"
    outside.touch()
    try:
        (root / "agent.py").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted")
    url = f"/api/v1/projects/{p['id']}/agent"
    assert client.put(url, json=registration(root)).status_code == 200
    assert client.post(url + "/check").json()["configuration_status"] == "unavailable"


def test_git_metadata_is_read_when_repository_exists(client, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "initial"], check=True)
    (tmp_path / "python").touch()
    (tmp_path / "agent.py").touch()
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    client.put(url, json=registration(tmp_path))
    report = client.post(url + "/check").json()
    assert len(report["git_commit"]) == 40
    assert report["git_dirty"] is None


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_git_check_reads_packed_ref_without_running_filters(client, tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "agent.py").write_text("initial")
    subprocess.run(["git", "-C", str(tmp_path), "add", "agent.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "initial"], check=True)
    expected = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(tmp_path), "pack-refs", "--all"], check=True)
    (tmp_path / "python").touch()
    (tmp_path / "agent.py").touch()
    (tmp_path / "agent.py").write_text("modified")
    marker = tmp_path / "filter-executed"
    (tmp_path / ".gitattributes").write_text("*.py filter=evil\n")
    subprocess.run(["git", "-C", str(tmp_path), "config", "filter.evil.clean", f"sh -c 'echo ran > {marker.as_posix()}'"], check=True)
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    client.put(url, json=registration(tmp_path))
    def forbidden_subprocess(*args, **kwargs):
        raise AssertionError("configuration check must not launch any process")
    monkeypatch.setattr(subprocess, "run", forbidden_subprocess)
    report = client.post(url + "/check").json()
    assert report["configuration_status"] == "ready"
    assert report["git_commit"] == expected
    assert report["git_dirty"] is None
    assert not marker.exists()





def test_config_rejects_authorization_but_allows_max_tokens(client, tmp_path):
    p = project(client)
    url = f"/api/v1/projects/{p['id']}/agent"
    safe = client.put(url, json=registration(tmp_path, config={"max_tokens": 1024, "temperature": 0.2}))
    assert safe.status_code == 200
    assert safe.json()["config"]["max_tokens"] == 1024
    for key in ("Authorization", "proxy-authorization", "access_token", "refreshToken"):
        response = client.put(url, json=registration(tmp_path, config={"headers": {key: "sensitive-value"}}))
        assert response.status_code == 422
        assert "sensitive-value" not in response.text
