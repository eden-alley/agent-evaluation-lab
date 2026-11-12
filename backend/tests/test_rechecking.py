"""Saved-delivery checks: no Agent calls, immutable inputs and independent records."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lab.main import create_app

CASE = "U05-click-default-help"


class Executor:
    def __init__(self):
        self.calls = []
        self.failure = False

    def identity(self):
        return {"backend": "offline-test", "python": "test-python", "sandbox": "test-sandbox"}

    def run(self, workspace, suite):
        self.calls.append((workspace, suite))
        assert workspace.name != "workspace"
        assert (workspace / "_tmp_patch.py").read_bytes() == b"raise Exception('never execute')"
        if self.failure:
            raise RuntimeError("sandbox unavailable")
        return {"suite": suite, "exit_code": 1, "tests": 3 if suite == "public" else 1,
                "failures": 1, "errors": 0, "skipped": 0, "successful": False,
                "stdout": "test_help ... FAIL\n", "stderr": "", "seconds": 0.01}


@pytest.fixture
def rechecking(tmp_path, monkeypatch):
    app = create_app(tmp_path / "lab.sqlite3")
    executor = Executor()
    app.state.recheck_executor = executor
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "saved delivery fixture"}).json()
        root = tmp_path / "evaluation-runs" / "old-run"
        root.mkdir(parents=True)
        definition = {"id": CASE, "allowed_changed_paths": ["click/core.py"],
                      "files": [{"path": "click/core.py", "sha256": "old"},
                                {"path": "app.py", "sha256": hashlib.sha256(b"app").hexdigest()}],
                      "checks": [{"id": name, "rule": name, "dimension": "test",
                                  "required_for_task": name not in ("minimality", "efficiency"),
                                  "applicable": True, "method": "code"} for name in
                                 ("result", "scope", "delivery", "self_test", "localization", "repeatable", "minimality", "efficiency")]}
        from lab.rechecking import checker
        from lab.quality_checks import digest
        monkeypatch.setattr(checker, "SUPPORTED_TASK_HASH", digest(definition))
        entries = []

        def artifact(path, value):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            entries.append({"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})

        prefix = f"saved/{CASE}"
        artifact(f"cases/{CASE}/case.json", definition)
        final_files = {}
        for name, content in {"click/core.py": b"unchanged bug", "app.py": b"app", "_tmp_patch.py": b"raise Exception('never execute')"}.items():
            artifact(f"{prefix}/workspace/{name}", content)
            final_files[name] = hashlib.sha256(content).hexdigest()
        artifact(f"{prefix}/result.json", {"id": CASE, "final_files": final_files, "requests": 30,
                                            "phases": [{"stop_reason": "max_steps"}]})
        events = [{"type": "task_stopped", "event_id": 1, "reason": "max_steps", "files": final_files}]
        artifact(f"{prefix}/events.jsonl", (json.dumps(events[0]) + "\n").encode())
        checks = [{**c, "value": 0, "reason": "historical failure"} for c in definition["checks"]]
        run = {"id": "old-run", "project_id": project["id"], "dataset": {"id": "frozen-v1", "content_hash": "a" * 64},
               "cases": [{"id": CASE, "title": "Click default help", "checks": checks, "files": entries}], "files": []}
        (root / "run.json").write_text(json.dumps(run), encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({"files": entries}), encoding="utf-8")
        yield client, root, executor, artifact, entries


def bind(client, request_id="bind-1"):
    return client.post(f"/api/v1/evaluation-runs/old-run/cases/{CASE}/checker-bindings", json={
        "request_id": request_id, "package_id": "click-help", "package_version": "1.0.0"})


def start(client, binding_id, request_id="check-1"):
    return client.post("/api/v1/evaluation-runs/old-run/check-runs", json={"request_id": request_id, "binding_id": binding_id})


def test_binds_and_rechecks_old_delivery_without_changing_archive(rechecking):
    client, root, executor, _, _ = rechecking
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    binding = bind(client)
    assert binding.status_code == 201, binding.text
    b = binding.json()
    assert b["snapshot"]["task"]["case_id"] == CASE
    assert b["snapshot"]["package"]["content_hash"]
    assert bind(client).json()["id"] == b["id"]
    created = start(client, b["id"])
    assert created.status_code == 201, created.text
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created.json()['id']}").json()
    assert saved["status"] == "completed", saved
    report = saved["report"]
    assert report["agent_model_requests"] == report["judge_model_requests"] == 0
    assert report["core_acceptance"] == "fail"
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["result"]["value"] == 0
    assert checks["scope"]["value"] == 1
    assert checks["self_test"]["value"] == 0
    assert checks["repeatable"]["value"] == "unknown"
    assert checks["minimality"]["value"] == "unknown"
    assert checks["repeatable"]["historical_value"] == 0
    assert len(executor.calls) == 2
    assert start(client, b["id"]).json()["id"] == saved["id"]
    assert len(executor.calls) == 2
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    context = client.get(f"/api/v1/evaluation-runs/old-run/cases/{CASE}/checker").json()
    assert len(context["bindings"]) == len(context["runs"]) == 1


def test_source_tampering_and_stale_binding_are_not_agent_failures(rechecking):
    client, root, executor, _, _ = rechecking
    b = bind(client).json()
    (root / f"saved/{CASE}/workspace/click/core.py").write_text("tampered", encoding="utf-8")
    response = start(client, b["id"])
    assert response.status_code == 409, response.text
    assert not executor.calls


def test_executor_failure_has_no_agent_score(rechecking):
    client, _, executor, _, _ = rechecking
    executor.failure = True
    b = bind(client).json()
    created = start(client, b["id"]).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    assert saved["status"] == "failed"
    assert saved["report"] is None
    assert saved["error"]["code"] == "CHECK_EXECUTION_FAILED"


def test_zero_tests_is_execution_error_not_pass(rechecking):
    client, _, executor, _, _ = rechecking
    executor.run = lambda workspace, suite: {"suite": suite, "exit_code": 0, "tests": 0, "successful": True}
    b = bind(client).json()
    created = start(client, b["id"]).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    assert saved["status"] == "failed" and saved["report"] is None


def test_unknown_package_and_unsupported_case_cannot_execute(rechecking):
    client, _, executor, _, _ = rechecking
    response = client.post(f"/api/v1/evaluation-runs/old-run/cases/{CASE}/checker-bindings", json={
        "request_id": "bad", "package_id": "arbitrary-command", "package_version": "1"})
    assert response.status_code == 422
    response = client.post("/api/v1/evaluation-runs/old-run/cases/OTHER/checker-bindings", json={
        "request_id": "bad", "package_id": "click-help", "package_version": "1.0.0"})
    assert response.status_code == 404
    assert not executor.calls


def test_successful_external_retest_cannot_create_agent_self_test(rechecking):
    client, _, executor, _, _ = rechecking
    def passing(workspace, suite):
        return {"suite": suite, "exit_code": 0, "tests": 3 if suite == "public" else 1,
                "failures": 0, "errors": 0, "skipped": 0, "successful": True}
    executor.run = passing
    b = bind(client).json()
    created = start(client, b["id"]).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    checks = {c['id']: c for c in saved['report']['checks']}
    assert checks['result']['value'] == 1
    assert checks['self_test']['value'] == 0
    assert checks['repeatable']['value'] == 'unknown'
    assert saved['report']['core_acceptance'] == 'fail'


def test_check_artifacts_are_hash_verified_and_path_restricted(rechecking):
    client, root, _, _, _ = rechecking
    created = start(client, bind(client).json()['id']).json()
    prefix = f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}/artifact"
    assert client.get(prefix, params={'path': 'public.json'}).status_code == 200
    assert client.get(prefix, params={'path': '../lab.sqlite3'}).status_code == 404
    assert client.get(prefix, params={'path': 'private.json'}).status_code == 404
    output = root.parent.parent / 'check-runs' / created['id'] / 'public.json'
    output.write_text('tampered', encoding='utf-8')
    assert client.get(prefix, params={'path': 'public.json'}).status_code == 409


def test_environment_drift_requires_a_new_binding(rechecking):
    client, _, executor, _, _ = rechecking
    b = bind(client).json()
    executor.identity = lambda: {'backend': 'changed'}
    created = start(client, b['id']).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    assert saved['status'] == 'failed' and saved['report'] is None
    assert not executor.calls


def test_missing_trace_retains_unknown_instead_of_inventing_a_failure(rechecking):
    client, root, _, _, _ = rechecking
    run = json.loads((root / 'run.json').read_text())
    run['cases'][0]['files'] = [f for f in run['cases'][0]['files'] if not f['path'].endswith('events.jsonl')]
    (root / 'run.json').write_text(json.dumps(run))
    created = start(client, bind(client).json()['id']).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    checks = {c['id']: c for c in saved['report']['checks']}
    assert checks['self_test']['value'] == 'unknown'


def test_another_binding_cannot_reuse_a_check_request(rechecking):
    client, _, _, _, _ = rechecking
    first, second = bind(client).json(), bind(client, 'bind-2').json()
    assert start(client, first['id']).status_code == 201
    assert start(client, second['id']).status_code == 409


@pytest.mark.parametrize('command,output,expected', [
    ('python -B -m unittest discover -s tests -v', 'Ran 0 tests in 0.0s\n\nOK', 0),
    ('python -B -m unittest discover -s unrelated -v', 'Ran 3 tests in 0.0s\n\nOK', 0),
    ('python -B -m unittest discover -s tests -v', 'Ran 3 tests in 0.0s\n\nOK', 1),
    ('python -B -m unittest discover -s tests -p test_regression.py -v', 'Ran 3 tests in 0.0s\n\nOK', 0),
    ('python -B -m unittest discover -s tests -v', 'Ran 3 tests in 0.0s\n\nOK (skipped=3)', 0),
])
def test_original_self_test_requires_real_public_suite(command, output, expected):
    from lab.rechecking.checker import original_self_test
    final = {'click/core.py': 'hash'}
    events = [
        {'type': 'tool_call', 'event_id': 1, 'tool': 'run_shell', 'call_id': 'x', 'arguments': json.dumps({'command': command}), 'files': final},
        {'type': 'tool_result', 'event_id': 2, 'tool': 'run_shell', 'call_id': 'x', 'ok': True, 'exit_code': 0, 'data': output, 'files': final},
        {'type': 'task_stopped', 'event_id': 3, 'files': final},
    ]
    value, matches = original_self_test({'events': events, 'result': {'final_files': final},
        'definition': {'allowed_changed_paths': ['click/core.py']}})
    assert value == expected and bool(matches) == bool(expected)


def test_deleted_empty_protected_file_fails_scope():
    from lab.rechecking.checker import results
    data = {'case': {'id': CASE}, 'initial': {'click/py.typed': hashlib.sha256(b'').hexdigest()},
            'workspace': {}, 'result': {'final_files': {}}, 'events': [], 'task_path': 'case.json',
            'trace_path': 'events.jsonl', 'result_path': 'result.json',
            'definition': {'allowed_changed_paths': [], 'checks': [{'id': 'scope', 'required_for_task': True}]}}
    report = results(data, [{'successful': True}, {'successful': True}], [])
    assert report['checks'][0]['value'] == 0


def test_delivered_code_runtime_errors_fail_task_instead_of_losing_all_scores(rechecking):
    client, _, executor, _, _ = rechecking
    executor.run = lambda workspace, suite: {'suite': suite, 'exit_code': 1,
        'tests': 3 if suite == 'public' else 1, 'failures': 0, 'errors': 1,
        'skipped': 0, 'successful': False}
    created = start(client, bind(client).json()['id']).json()
    saved = client.get(f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}").json()
    assert saved['status'] == 'completed'
    assert saved['report']['core_acceptance'] == 'fail'
    assert next(c for c in saved['report']['checks'] if c['id'] == 'result')['value'] == 0


def test_completed_history_remains_readable_when_original_source_changes(rechecking):
    client, root, _, _, _ = rechecking
    b = bind(client).json()
    created = start(client, b['id']).json()
    path = f"/api/v1/evaluation-runs/old-run/check-runs/{created['id']}"
    original = client.get(path).json()['report']
    (root / f'saved/{CASE}/workspace/click/core.py').write_text('changed')
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()['source_state'] == 'changed'
    assert response.json()['report'] == original
    assert client.get(path + '/artifact', params={'path': 'public.json'}).status_code == 200
    assert start(client, b['id'], 'new').status_code == 409


def test_concurrent_identical_binding_requests_return_one_binding(rechecking):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    client, _, executor, _, _ = rechecking
    identity = executor.identity
    barrier = threading.Barrier(2)
    def simultaneous():
        barrier.wait(timeout=10)
        return identity()
    executor.identity = simultaneous
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: bind(client), range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()['id'] == responses[1].json()['id']


def test_concurrent_check_requests_do_not_execute_twice(rechecking, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from lab.rechecking import routes
    client, _, executor, _, _ = rechecking
    b = bind(client).json()
    original = routes.validate
    barrier = threading.Barrier(2)
    def simultaneous(*args):
        value = original(*args)
        barrier.wait(timeout=10)
        return value
    monkeypatch.setattr(routes, 'validate', simultaneous)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: start(client, b['id']), range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()['id'] == responses[1].json()['id']
    assert len(executor.calls) == 2
