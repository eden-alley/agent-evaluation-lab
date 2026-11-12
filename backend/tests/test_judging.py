"""Offline Judge contracts, provenance, routing and evidence integrity."""
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from lab.main import create_app


@pytest.fixture
def judging(tmp_path):
    app = create_app(tmp_path / "lab.sqlite3")
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "judge offline"}).json()
        version = client.post("/api/v1/skills/dataset-design/versions",
            json={"content": "Offline grading fixture", "change_note": "test"}).json()
        client.post(f"/api/v1/skills/dataset-design/versions/{version['id']}/publish")
        skill = {"skill_id": "dataset-design", "version_id": version["id"], "content_hash": version["content_hash"]}
        folder = tmp_path / "evaluation-runs" / "real-run"
        folder.mkdir(parents=True)
        checks = [
            {"id": "compare", "dimension": "结果质量", "rule": "产品事实正确", "value": 1,
             "automatic_value": 0, "reason": "名称是允许的表达", "review_method": "历史 AI 复核",
             "method": "code", "required_for_task": True},
            {"id": "repeatable", "dimension": "可复现", "rule": "验证结果可重建",
             "value": "unknown", "reason": "缺少结果基准", "method": "code", "required_for_task": False},
        ]
        evidence = json.dumps({"checks": checks}, ensure_ascii=False)
        (folder / "reviewed-score.json").write_text(evidence, encoding="utf-8")
        (folder / "manifest.json").write_text(json.dumps({"files": [
            {"path": "reviewed-score.json", "bytes": len(evidence.encode()), "sha256": hashlib.sha256(evidence.encode()).hexdigest()}
        ]}), encoding="utf-8")
        data = {"id": "real-run", "project_id": project["id"], "dataset": {"version": 1},
                "method": "historical method", "cases": [{"id": "O10", "title": "不可信资料",
                "checks": checks, "files": [{"path": "reviewed-score.json"}]}]}
        (folder / "run.json").write_text(json.dumps(data), encoding="utf-8")
        payload = {"request_id": "archive-1", "case_ids": ["O10"], "mode": "archive", "skill": skill}
        yield client, folder, payload


def start(judging, **changes):
    client, _, base = judging
    return client.post("/api/v1/evaluation-runs/real-run/judgments", json={**base, **changes})


def report(judging, job):
    return judging[0].get(f"/api/v1/evaluation-runs/real-run/judgments/{job['id']}").json()


def test_archive_and_mock_are_separate_and_unknown_is_not_pending(judging):
    created = start(judging)
    assert created.status_code == 201, created.text
    saved = report(judging, created.json())
    assert saved["status"] == "completed"
    case = saved["report"]["cases"][0]
    assert case["checks"][0]["value"] == 1
    assert case["checks"][0]["review_state"] == "historical"
    assert case["checks"][1]["review_state"] == "missing_evidence"
    assert case["core_acceptance"] == "pass"
    simulated = report(judging, start(judging, mode="mock", request_id="mock-1").json())
    row = simulated["report"]["cases"][0]["checks"][0]
    assert row["automatic_value"] == 0 and row["judge_value"] == 1
    assert row["value"] == "unknown" and row["review_state"] == "pending"
    assert simulated["report"]["cases"][0]["core_acceptance"] == "pending_review"
    assert simulated["report"]["is_simulation"] is True
    assert "human" not in row["source"]
    assert saved["report"]["skill"] == judging[2]["skill"]


def test_idempotency_and_payload_conflict(judging):
    first = start(judging)
    assert start(judging).json()["id"] == first.json()["id"]
    assert start(judging, mode="mock").status_code == 409
    assert start(judging, case_ids=["missing"], request_id="other").status_code == 404
    assert start(judging, case_ids=["O10", "O10"], request_id="duplicate").status_code == 422


def test_review_is_append_only_and_compare_and_swap(judging):
    job = start(judging, mode="mock", request_id="mock-review").json()
    url = f"/api/v1/evaluation-runs/real-run/judgments/{job['id']}/reviews"
    change = {"case_id": "O10", "check_id": "compare", "value": 1,
              "reason": "人工确认允许产品全名", "revision": 0, "request_id": "review-1"}
    response = judging[0].post(url, json=change)
    assert response.status_code == 200, response.text
    assert judging[0].post(url, json=change).json()["revision"] == 1
    assert judging[0].post(url, json={**change, "request_id": "review-2", "value": 0}).status_code == 409
    saved = report(judging, job)
    assert saved["report"]["cases"][0]["checks"][0]["value"] == 1
    assert saved["report"]["cases"][0]["checks"][0]["review_state"] == "resolved"
    assert saved["report"]["cases"][0]["core_acceptance"] == "pass"
    assert len(saved["reviews"]) == 1


def test_rejects_changed_evidence_and_changed_run(judging):
    client, folder, _ = judging
    job = start(judging).json()
    (folder / "reviewed-score.json").write_text("changed", encoding="utf-8")
    path = f"/api/v1/evaluation-runs/real-run/judgments/{job['id']}"
    assert client.get(path).status_code == 409
    response = start(judging, request_id="tampered")
    assert report(judging, response.json())["status"] == "failed"


def test_unpublished_or_wrong_skill_reference_is_rejected(judging):
    payload = judging[2]
    wrong = {**payload["skill"], "content_hash": "0" * 64}
    assert start(judging, skill=wrong).status_code == 422

def test_unrelated_attachment_cannot_prove_a_grade():
    from lab.judging import normalize_case
    case = {"id": "missing-primary", "checks": [
        {"id": "result", "rule": "测试通过", "required_for_task": True,
         "value": 1, "evidence": "missing-test.json", "reason": "测试应通过"}]}
    refs = [{"path": "CASE.md", "label": "CASE.md", "excerpt": "只有题面", "sha256": "x"}]
    row = normalize_case(case, "archive", refs)["checks"][0]
    assert row["archive_value"] == 1
    assert row["value"] == "unknown"
    assert row["review_state"] == "missing_evidence"


def test_historical_evidence_is_labelled_as_inherited(judging):
    job = start(judging).json()
    saved = report(judging, job)
    check = saved["report"]["cases"][0]["checks"][0]
    assert check["evidence_state"] == "inherited"
    assert check["archive_value"] == 1


def test_manual_unknown_keeps_visible_evidence_gap_and_history(judging):
    job = start(judging, mode="mock", request_id="manual-unknown").json()
    path = f"/api/v1/evaluation-runs/real-run/judgments/{job['id']}/reviews"
    response = judging[0].post(path, json={"case_id": "O10", "check_id": "compare",
        "value": "unknown", "reason": "需要追加材料", "revision": 0, "request_id": "human-u"})
    assert response.status_code == 200
    saved = response.json()
    check = saved["report"]["cases"][0]["checks"][0]
    assert check["review_state"] == "resolved"
    assert check["evidence_state"] == "insufficient"
    assert saved["report"]["cases"][0]["core_acceptance"] == "unknown"
    second = judging[0].post(path, json={"case_id": "O10", "check_id": "compare",
        "value": 1, "reason": "核对材料后确认通过", "revision": 1, "request_id": "human-2"})
    assert second.status_code == 200
    assert len(second.json()["reviews"]) == 2

def test_mcp_summary_does_not_duplicate_full_artifacts(judging):
    from lab.mcp_server import compact_judgment, excerpt_evidence
    saved = report(judging, start(judging).json())
    summary = compact_judgment(saved)
    assert "checks" not in summary["cases"][0]
    assert "skill_snapshot" not in summary["report"]
    full_case = compact_judgment(saved, "O10")
    refs = full_case["cases"][0]["checks"][0]["evidence"]
    assert refs and all("excerpt" not in ref and "path" in ref for ref in refs)
    assert excerpt_evidence({"content": "first\nsecond\nthird", "path": "a"}, 2, 1)["content"] == "second"



