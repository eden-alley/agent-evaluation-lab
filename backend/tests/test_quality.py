import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from lab.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "quality.sqlite3")) as value:
        yield value


def draft_payload(client, **changes):
    project = client.post("/api/v1/projects", json={"name": "质量测试项目", "description": "检查端口读取"}).json()
    return {"project_id": project["id"], "name": "端口读取", "task_description": "准确读取配置中的端口",
            "requirements": [{"id": "r1", "description": "返回配置中的端口"}],
            "cases": [{"case_id": "c1", "title": "读取端口", "input": {"prompt": "读取端口"},
                       "expected": {"port": 8080}, "categories": ["文件"], "requirement_ids": ["r1"],
                       "grading_notes": "port 字段等于 8080"}],
            "source": {"client": "offline-test"}, "request_id": "draft-1", **changes}


def create_draft(client, payload=None):
    result = client.post("/api/v1/dataset-drafts", json=payload or draft_payload(client))
    assert result.status_code == 201, result.text
    return result.json()


def report_payload(draft, **changes):
    return {"request_id": "report-1", "draft_hash": draft["content_hash"],
            "source": {"client": "offline-test"}, "summary": "测试报告，不代表真实模型检查。",
            "reviewed_case_ids": [c["case_id"] for c in draft["payload"]["cases"]],
            "coverage": [{"requirement_id": "r1", "status": "covered", "case_ids": ["c1"], "reason": "用例检查端口"}],
            "findings": [], **changes}


def submit_report(client, draft, payload=None):
    result = client.post(f"/api/v1/dataset-drafts/{draft['id']}/reports", json=payload or report_payload(draft))
    assert result.status_code == 201, result.text
    return result.json()


def decision(client, draft, report, **changes):
    return client.post(f"/api/v1/dataset-drafts/{draft['id']}/decision", json={
        "decision": "approve", "report_id": report["id"], "note": "", **changes})


def test_roundtrip_publication_is_immutable_and_persistent(client):
    draft = create_draft(client)
    assert draft["status"] == "pending"
    assert draft["metrics"]["total_cases"] == 1
    assert draft["metrics"]["reviewed_cases"] == 0
    report = submit_report(client, draft)
    published = decision(client, draft, report)
    assert published.status_code == 200, published.text
    version = published.json()["version"]
    assert version["version"] == 1 and version["content_hash"] == draft["content_hash"]
    assert version["quality_report"]["id"] == report["id"]
    assert client.get(f"/api/v1/dataset-versions/{version['id']}").json() == version
    assert client.post(f"/api/v1/dataset-drafts/{draft['id']}/reports", json=report_payload(draft, request_id="late")).status_code == 409
    assert client.get(f"/api/v1/projects/{draft['project_id']}/dataset-versions").json()["items"][0]["id"] == version["id"]
    with TestClient(create_app(client.app.state.db_path)) as reopened:
        assert reopened.get(f"/api/v1/dataset-versions/{version['id']}").json() == version


def test_validation_is_atomic_and_structured(client):
    payload = draft_payload(client)
    payload["cases"].append(copy.deepcopy(payload["cases"][0]))
    result = client.post("/api/v1/dataset-drafts", json=payload)
    assert result.status_code == 422
    assert result.json()["error"]["details"]
    assert client.get(f"/api/v1/projects/{payload['project_id']}/dataset-drafts").json()["items"] == []
    payload["cases"].pop()
    payload["cases"][0]["requirement_ids"] = ["unknown"]
    assert client.post("/api/v1/dataset-drafts", json=payload).status_code == 422
    payload["cases"][0]["requirement_ids"] = ["r1"]
    payload["cases"][0]["input"] = {"bad": float("nan")}
    # Send non-standard JSON directly; strict canonical storage must reject NaN.
    import json
    assert client.post("/api/v1/dataset-drafts", content=json.dumps(payload)).status_code == 422


def test_idempotency_conflict_and_identical_retries(client):
    payload = draft_payload(client)
    draft = create_draft(client, payload)
    again = client.post("/api/v1/dataset-drafts", json=payload)
    assert again.status_code == 201 and again.json()["id"] == draft["id"]
    payload["cases"][0]["title"] = "变更"
    assert client.post("/api/v1/dataset-drafts", json=payload).status_code == 409
    report = report_payload(draft)
    saved = submit_report(client, draft, report)
    assert submit_report(client, draft, report)["id"] == saved["id"]
    report["summary"] = "修改报告"
    assert client.post(f"/api/v1/dataset-drafts/{draft['id']}/reports", json=report).status_code == 409


def test_reports_require_matching_hash_and_local_evidence(client):
    draft = create_draft(client)
    url = f"/api/v1/dataset-drafts/{draft['id']}/reports"
    assert client.post(url, json=report_payload(draft, draft_hash="0"*64)).status_code == 409
    assert client.post(url, json=report_payload(draft, reviewed_case_ids=["other-case"])).status_code == 422
    finding = {"id": "f1", "severity": "warning", "category": "ambiguity", "case_ids": ["c1"],
               "requirement_ids": [], "evidence": [{"target_type": "case", "target_id": "c1", "field": "input", "quote": "不存在的原文"}],
               "explanation": "措辞问题", "suggestion": "明确路径"}
    assert client.post(url, json=report_payload(draft, findings=[finding])).status_code == 422
    finding["evidence"][0]["quote"] = "读取端口"
    assert submit_report(client, draft, report_payload(draft, findings=[finding]))["payload"]["findings"][0]["id"] == "f1"


def test_partial_review_stale_report_and_blockers_cannot_publish(client):
    draft = create_draft(client)
    partial = submit_report(client, draft, report_payload(draft, reviewed_case_ids=[], coverage=[{
        "requirement_id": "r1", "status": "not_assessed", "case_ids": [], "reason": "未检查"}]))
    assert decision(client, draft, partial, note="不能绕过").status_code == 409
    current = submit_report(client, draft, report_payload(draft, request_id="report-2"))
    assert decision(client, draft, partial).status_code == 409
    blocking = {"id": "block", "severity": "blocker", "category": "ground_truth", "case_ids": ["c1"], "requirement_ids": [],
                "evidence": [{"target_type": "case", "target_id": "c1", "field": "expected", "quote": "8080"}],
                "explanation": "测试用阻断项", "suggestion": "核对原始配置"}
    latest = submit_report(client, draft, report_payload(draft, request_id="report-3", findings=[blocking]))
    assert decision(client, draft, latest, note="不能绕过阻断").status_code == 409
    assert decision(client, draft, current).status_code == 409


def test_warnings_need_acknowledgement_and_duplicate_inputs_detected(client):
    payload = draft_payload(client)
    second = copy.deepcopy(payload["cases"][0]); second["case_id"] = "c2"
    payload["cases"].append(second)
    draft = create_draft(client, payload)
    assert any(f["category"] == "duplicate_input" for f in draft["checks"])
    report = submit_report(client, draft)
    assert decision(client, draft, report).status_code == 409
    assert decision(client, draft, report, note="已知重复，保留用于后续调整").status_code == 200


def test_stale_base_version_and_cross_project_reference_rejected(client):
    payload = draft_payload(client)
    draft = create_draft(client, payload)
    competing = create_draft(client, {**payload, "request_id": "other"})
    report = submit_report(client, draft)
    other_report = submit_report(client, competing)
    version = decision(client, draft, report).json()["version"]
    assert decision(client, competing, other_report).status_code == 409
    next_draft = create_draft(client, {**payload, "base_version_id": version["id"], "request_id": "v2"})
    next_report = submit_report(client, next_draft)
    assert decision(client, next_draft, next_report).json()["version"]["version"] == 2
    wrong_project = draft_payload(client, base_version_id=version["id"])
    assert client.post("/api/v1/dataset-drafts", json=wrong_project).status_code == 409


def test_rejection_keeps_evidence_and_prevents_later_mutation(client):
    draft = create_draft(client)
    report = submit_report(client, draft)
    result = decision(client, draft, report, decision="reject", note="需要补充边界场景")
    assert result.status_code == 200 and result.json()["draft"]["status"] == "rejected"
    stored = client.get(f"/api/v1/dataset-drafts/{draft['id']}").json()
    assert stored["latest_report"]["id"] == report["id"]
    assert stored["decision"]["note"] == "需要补充边界场景"
    assert decision(client, draft, report).status_code == 409


def test_existing_schema_migrates_without_losing_projects(tmp_path):
    path = tmp_path / "old.sqlite3"
    from lab.db import initialize
    from pathlib import Path
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parents[1] / "lab/migrations/001_initial.sql").read_text())
        conn.execute("INSERT INTO projects VALUES ('old','Existing','','t','t')")
    initialize(path); initialize(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM projects WHERE id='old'").fetchone()[0] == "Existing"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM judgments").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("left,right", [(True, 1), (False, 0)])
def test_boolean_and_numeric_expectations_are_conflicting(client, left, right):
    payload = draft_payload(client)
    payload["cases"][0]["expected"] = {"ok": left}
    second = copy.deepcopy(payload["cases"][0])
    second["case_id"] = "c2"
    second["expected"] = {"ok": right}
    payload["cases"].append(second)
    draft = create_draft(client, payload)
    assert any(c["category"] == "conflicting_expectation" and c["severity"] == "blocker" for c in draft["checks"])
    report = submit_report(client, draft)
    assert decision(client, draft, report, note="不应能绕过类型冲突").status_code == 409


def test_concurrent_approvals_cannot_publish_two_versions_from_one_base(client):
    payload = draft_payload(client)
    first = create_draft(client, payload)
    second = create_draft(client, {**payload, "request_id": "competing"})
    a, b = submit_report(client, first), submit_report(client, second)
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(decision, client, first, a), pool.submit(decision, client, second, b)]
        statuses = sorted(f.result().status_code for f in calls)
    assert statuses == [200, 409]
    assert len(client.get(f"/api/v1/projects/{first['project_id']}/dataset-versions").json()["items"]) == 1


def test_request_size_limit_rejects_body_before_parsing(client):
    response = client.post("/api/v1/dataset-drafts", content=b"x" * (2 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
