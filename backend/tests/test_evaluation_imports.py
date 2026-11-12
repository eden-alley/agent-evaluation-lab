"""Read-only external run imports: persistence, evidence integrity, isolation."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from lab.main import create_app


@pytest.fixture
def imported(tmp_path):
    app = create_app(tmp_path / "lab.sqlite3")
    with TestClient(app) as client:
        project = client.post('/api/v1/projects', json={'name': 'external evidence'}).json()
        root = tmp_path / 'evaluation-runs' / 'real-run'
        root.mkdir(parents=True)
        content = '原始证据\n'
        data = {'id': 'real-run', 'project_id': project['id'], 'name': '真实导入',
                'case_count': 1, 'cases': [{'id': 'C04', 'checks': [{'value': 'unknown'}]}]}
        (root / 'run.json').write_text(json.dumps(data), encoding='utf-8')
        (root / 'evidence.txt').write_bytes(content.encode('utf-8'))
        raw = (root / 'evidence.txt').read_bytes()
        (root / 'manifest.json').write_text(json.dumps({'files': [{'path': 'evidence.txt',
              'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}]}), encoding='utf-8')
        yield client, root, data


def test_real_runs_list_and_detail_preserve_unknown(imported):
    client, _, data = imported
    response = client.get('/api/v1/evaluation-runs')
    assert response.status_code == 200
    assert response.json()['items'][0]['id'] == data['id']
    assert 'cases' not in response.json()['items'][0]
    detail = client.get('/api/v1/evaluation-runs/real-run').json()
    assert detail['cases'][0]['checks'][0]['value'] == 'unknown'
    assert client.get('/api/v1/health').json()['capabilities']['evaluation_execution'] is False
    assert client.get('/api/v1/evaluation-runs?project_id=other').json()['items'] == []


def test_artifact_content_and_download(imported):
    client, _, _ = imported
    response = client.get('/api/v1/evaluation-runs/real-run/artifact', params={'path': 'evidence.txt'})
    assert response.status_code == 200
    assert response.json()['content'] == '原始证据\n'
    download = client.get('/api/v1/evaluation-runs/real-run/artifact', params={'path': 'evidence.txt', 'download': True})
    assert download.content == '原始证据\n'.encode()
    assert 'attachment' in download.headers['content-disposition']
    assert download.headers['x-content-type-options'] == 'nosniff'


def test_unlisted_or_traversal_file_is_not_read(imported):
    client, root, _ = imported
    (root / 'private.txt').write_text('private', encoding='utf-8')
    for path in ['private.txt', '../lab.sqlite3', '..\\lab.sqlite3', str(root / 'private.txt')]:
        response = client.get('/api/v1/evaluation-runs/real-run/artifact', params={'path': path})
        assert response.status_code == 404
    assert client.get('/api/v1/evaluation-runs/missing').status_code == 404


def test_modified_evidence_is_rejected(imported):
    client, root, _ = imported
    (root / 'evidence.txt').write_text('changed', encoding='utf-8')
    response = client.get('/api/v1/evaluation-runs/real-run/artifact', params={'path': 'evidence.txt'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'EVIDENCE_CHANGED'


def test_trace_retains_test_failure_and_links_to_original_inputs(imported):
    client, root, data = imported
    path = "C04/events.jsonl"
    rows = [
        {"type": "task_started", "event_id": 1, "phase": 1, "task": "检查测试"},
        {"type": "model_response", "event_id": 2, "phase": 1},
        {"type": "tool_call", "event_id": 3, "phase": 1, "call_id": "a", "tool": "run_shell",
         "arguments": '{"command":"run-check.cmd | more"}', "files": {"service.py": "old"}},
        {"type": "tool_result", "event_id": 4, "phase": 1, "call_id": "a",
         "ok": True, "data": "Ran 1 test\n\nFAILED (failures=1)", "files": {"service.py": "new"}},
        {"type": "task_started", "event_id": 1, "phase": 2, "task": "继续检查"},
    ]
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (root / "C04").mkdir()
    (root / path).write_bytes(raw)
    file = {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    data["cases"][0]["files"] = [file]
    (root / "run.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"files": [file]}), encoding="utf-8")
    url = "/api/v1/evaluation-runs/real-run/cases/C04/trace"
    response = client.get(url)
    assert response.status_code == 200
    trace = response.json()
    assert trace["source"] == path
    assert [row["line"] for row in trace["groups"]] == [1, 2, 5]
    step = trace["groups"][1]
    assert "存在失败" in step["text"] and "service.py" in step["text"]
    assert step["event_ids"] == [2, 3, 4]
    assert "run-check.cmd | more" in step["evidence"][0]["text"]
    assert "FAILED" in step["evidence"][1]["text"]
    (root / path).write_bytes(raw + b" ")
    assert client.get(url).status_code == 409
