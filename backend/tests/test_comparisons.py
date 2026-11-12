"""External analysis protocol; synthetic fixtures never call a model or a grader."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lab.main import create_app

CASE = "U05-click-default-help"


@pytest.fixture
def comparison_env(tmp_path):
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        project = client.post("/api/v1/projects", json={"name": "comparison protocol fixture"}).json()
        skill = client.post("/api/v1/skills", json={"name": "comparison workflow fixture",
            "description": "offline test", "kind": "evaluation"}).json()
        version = client.post(f"/api/v1/skills/{skill['id']}/versions",
            json={"content": "Read the paired evidence and report limitations.", "change_note": "fixture"}).json()
        client.post(f"/api/v1/skills/{skill['id']}/versions/{version['id']}/publish")
        folder = tmp_path / "evaluation-runs/baseline"
        folder.mkdir(parents=True)
        events = [{"type": "tool_call", "event_id": 1, "tool": "run_shell", "call_id": "a"},
                  {"type": "tool_result", "event_id": 2, "ok": False, "data": "AssertionError: 0"}]
        raw = "".join(json.dumps(e) + "\n" for e in events).encode()
        (folder / "events.jsonl").write_bytes(raw)
        file = {"path": "events.jsonl", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        case = {"id": CASE, "title": "Click帮助显示错误", "task": {"turns": [
            {"role": "user", "content": "修复帮助显示，保护原测试。"}]},
            "metrics": {"model_requests": 30, "prompt_tokens": 273758, "completion_tokens": 3888,
                        "elapsed_seconds": 74.84, "estimated_usd": None},
            "checks": [{"id": "result", "value": 0, "required_for_task": True}], "files": [file]}
        run = {"id": "baseline", "name": "offline baseline fixture", "project_id": project["id"],
               "model": "fixed-test-model", "dataset": {"version": 1}, "cases": [case]}
        (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
        (folder / "manifest.json").write_text(json.dumps({"files": [file]}), encoding="utf-8")
        payload = {"request_id": "plan-1", "name": "U05 离线验证", "objective": "验证逐题证据链",
                   "baseline_run_id": "baseline", "candidate": {"kind": "simulation", "fixture_id": "u05-offline-v1"},
                   "case_ids": [CASE], "workflow": {"skill_id": skill["id"], "version_id": version["id"],
                   "content_hash": version["content_hash"]},
                   "analyst": {"kind": "offline_fixture", "name": "scripted protocol validation"}}
        yield client, folder, payload


def create(env, **changes):
    response = env[0].post("/api/v1/comparisons", json={**env[2], **changes})
    assert response.status_code == 201, response.text
    return response.json()


def case_materials(env, plan):
    response = env[0].get(f"/api/v1/comparisons/{plan['id']}/cases/{CASE}")
    assert response.status_code == 200, response.text
    return response.json()


def analysis_payload(materials):
    refs = [next(m for m in materials[side]["materials"] if m["kind"] == "case_record")
            for side in ("baseline", "candidate")]
    return {"request_id": "case-1", "revision": 0, "summary": "模拟情景中编辑落地改善，尚未实测。",
            "observations": [{"id": "edit", "dimension": "文件编辑", "title": "修改落地",
                "outcome": "improved", "before": "修改未落地", "after": "模拟B假设修改成功",
                "reason": "仅用于离线验证报告流转。", "limits": "没有真实新版运行。",
                "evidence": [{"material_id": m["id"], "sha256": m["sha256"], "line_count": 12} for m in refs]}]}


def final_payload(analysis):
    refs = [{"case_id": CASE, "observation_id": "edit"}]
    return {"request_id": "final-1", "case_report_ids": [analysis["id"]],
        "summary": "离线模拟验证，不是实测能力结论。",
        "findings": [{"title": "修改落地变化", "outcome": "improved", "explanation": "模拟B假设修复完成。", "refs": refs}],
        "recommendations": [{"title": "先核查编辑反馈", "phenomenon": "原补丁匹配失败。",
            "cause_status": "hypothesis", "cause": "需核对匹配文本与运行条件。", "action": "只读检查编辑反馈，再选改动。",
            "priority_reason": "直接影响修复落地。", "validation": "后续取得同条件真实B。",
            "success_signals": "修复写入且有效验证。", "guardrails": "保护原有行为。", "refs": refs}]}


def test_pinned_sources_and_simulation_never_enter_real_run_list(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    assert plan["is_simulation"] is True
    assert plan["progress"]["received"] == 0
    materials = case_materials(comparison_env, plan)
    assert materials["baseline"]["metrics"]["tool_calls"] == 1
    assert materials["baseline"]["metrics"]["tool_errors"] == 1
    assert materials["candidate"]["is_simulation"] is True
    assert [r["id"] for r in client.get("/api/v1/evaluation-runs").json()["items"]] == ["baseline"]
    assert plan["workflow"]["content_hash"] == comparison_env[2]["workflow"]["content_hash"]


def test_per_case_and_final_reports_preserve_provenance_and_idempotency(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    assert create(comparison_env)["id"] == plan["id"]
    payload = analysis_payload(case_materials(comparison_env, plan))
    url = f"/api/v1/comparisons/{plan['id']}/cases/{CASE}/analyses"
    first = client.post(url, json=payload)
    assert first.status_code == 201, first.text
    assert client.post(url, json=payload).json()["id"] == first.json()["id"]
    assert client.post(url, json={**payload, "summary": "changed"}).status_code == 409
    final = client.post(f"/api/v1/comparisons/{plan['id']}/reports", json=final_payload(first.json()))
    assert final.status_code == 201, final.text
    report = final.json()
    assert report["is_simulation"] is True
    assert report["case_analyses"][0]["content"]["observations"][0]["evidence"][0]["excerpt"]
    detail = client.get(f"/api/v1/comparisons/{plan['id']}").json()
    assert detail["progress"]["received"] == 1 and detail["progress"]["assessed"] == 1
    assert detail["latest_report"]["id"] == report["id"]


def test_incomplete_or_stale_reports_cannot_finalize(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    url = f"/api/v1/comparisons/{plan['id']}"
    assert client.post(url + "/reports", json=final_payload({"id": "missing"})).status_code == 409
    payload = analysis_payload(case_materials(comparison_env, plan))
    first = client.post(url + f"/cases/{CASE}/analyses", json=payload).json()
    assert client.post(url + f"/cases/{CASE}/analyses", json={**payload, "request_id": "stale"}).status_code == 409
    second = client.post(url + f"/cases/{CASE}/analyses", json={**payload, "request_id": "next", "revision": 1})
    assert second.status_code == 201
    assert client.post(url + "/reports", json=final_payload(first)).status_code == 409


def test_evidence_scope_digest_and_invented_provenance_are_rejected(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    payload = analysis_payload(case_materials(comparison_env, plan))
    url = f"/api/v1/comparisons/{plan['id']}/cases/{CASE}/analyses"
    bad = json.loads(json.dumps(payload))
    bad["observations"][0]["evidence"][0]["sha256"] = "0" * 64
    assert client.post(url, json=bad).status_code == 409
    bad["observations"][0]["evidence"][0]["material_id"] = "arbitrary-file"
    assert client.post(url, json=bad).status_code == 404
    assert client.post(url, json={**payload, "is_simulation": False}).status_code == 422
    assert client.get(f"/api/v1/comparisons/{plan['id']}/cases/other").status_code == 404


def test_source_drift_blocks_new_analysis_but_keeps_saved_report(comparison_env):
    client, folder, _ = comparison_env
    plan = create(comparison_env)
    payload = analysis_payload(case_materials(comparison_env, plan))
    url = f"/api/v1/comparisons/{plan['id']}"
    first = client.post(url + f"/cases/{CASE}/analyses", json=payload).json()
    report = client.post(url + "/reports", json=final_payload(first)).json()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    saved = client.get(url + "/reports/" + report["id"])
    assert saved.status_code == 200 and saved.json()["source_state"] == "changed"
    assert saved.json()["case_analyses"][0]["content"]["observations"][0]["evidence"][0]["excerpt"]
    assert client.post(url + f"/cases/{CASE}/analyses", json={**payload, "request_id": "new", "revision": 1}).status_code == 409


def test_missing_candidate_and_unknown_observations_are_not_capability_gains(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env, candidate={"kind": "missing"})
    materials = case_materials(comparison_env, plan)
    assert materials["candidate"] is None
    m = materials["baseline"]["materials"][0]
    payload = {"request_id": "baseline-only", "revision": 0, "summary": "等待新版运行。",
        "observations": [{"id": "edit", "dimension": "文件编辑", "title": "修改落地",
            "outcome": "insufficient", "before": "未落地", "after": None, "reason": "B缺失。", "evidence": []}]}
    url = f"/api/v1/comparisons/{plan['id']}"
    first = client.post(url + f"/cases/{CASE}/analyses", json=payload)
    assert first.status_code == 201, first.text
    detail = client.get(url).json()
    assert detail["progress"]["collection_complete"] is True
    assert detail["progress"]["assessed"] == 0 and detail["state"] == "waiting_candidate"
    forged = json.loads(json.dumps(payload))
    forged["request_id"], forged["revision"] = "forged", 1
    forged["observations"][0]["outcome"] = "improved"
    forged["observations"][0]["evidence"] = [{"material_id": m["id"], "sha256": m["sha256"]}]
    assert client.post(url + f"/cases/{CASE}/analyses", json=forged).status_code == 422


def test_changed_original_file_blocks_even_an_embedded_record_reference(comparison_env):
    client, folder, _ = comparison_env
    plan = create(comparison_env)
    payload = analysis_payload(case_materials(comparison_env, plan))
    (folder / "events.jsonl").write_text("changed outside manifest", encoding="utf-8")
    response = client.post(f"/api/v1/comparisons/{plan['id']}/cases/{CASE}/analyses", json=payload)
    assert response.status_code == 409, response.text


def test_packaged_workflow_matches_the_actual_skill_api_hash(comparison_env):
    root = Path(__file__).parents[2]
    entry = next(e for e in json.loads((root / "skills/catalog.json").read_text(encoding="utf-8"))["skills"]
                 if e["slug"] == "agent-version-comparison-workflow")
    payload = json.loads((root / "skills" / entry["payload_file"]).read_text(encoding="utf-8"))
    client = comparison_env[0]
    skill = client.post("/api/v1/skills", json=entry["catalog"]).json()
    saved = client.post(f"/api/v1/skills/{skill['id']}/versions", json=payload)
    assert saved.status_code == 201, saved.text
    assert saved.json()["content_hash"] == entry["platform_content_hash"]
