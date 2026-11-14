"""Selected task explanations are evidence-backed report content, never new grades."""
from copy import deepcopy
import json

import pytest
from lab.comparisons import review
from lab.quality_checks import digest
from test_comparisons import comparison_env, create, CASE
from test_capability_review import prepare, document, envelope


def explanation():
    return {"case_id": CASE, "focus": "baseline", "background": "用户希望修复命令行帮助显示，并保留原测试。",
        "stages": [{"title": "执行检查后收到失败反馈", "text": "Agent调用命令执行检查，工具返回AssertionError；本段只描述已有记录。",
            "evidence": [{"side": "baseline", "path": "events.jsonl", "event_id": 2}]}],
        "result": {"text": "基线检查未通过；尚无成功交付的证据。",
            "evidence": [{"side": "baseline", "path": "case-record.json", "check_id": "result"}]},
        "limitations": ["只讲解A原运行；B是模拟来源，不能推断实测变化。"]}


def explained_document():
    return {**document(), "case_explanations": [explanation()]}


def test_model_reply_locator_counts_responses_not_events(comparison_env):
    import hashlib
    client, folder, _ = comparison_env
    records = [{'type': 'model_response', 'event_id': 10},
               {'type': 'tool_call', 'event_id': 21},
               {'type': 'model_response', 'event_id': 30},
               {'type': 'tool_result', 'event_id': 41, 'ok': True, 'data': 'fixed'}]
    raw = ''.join(json.dumps(row) + '\n' for row in records).encode()
    (folder / 'events.jsonl').write_bytes(raw)
    descriptor = {'path': 'events.jsonl', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    run = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    run['cases'][0]['files'] = [descriptor]
    (folder / 'run.json').write_text(json.dumps(run), encoding='utf-8')
    (folder / 'manifest.json').write_text(json.dumps({'files': [descriptor]}), encoding='utf-8')
    plan = create(comparison_env)
    packet = prepare(client, plan['id'])
    doc = explained_document()
    doc['case_explanations'][0]['stages'][0]['evidence'] = [
        {'side': 'baseline', 'path': 'events.jsonl', 'event_id': 41}]
    response = client.post(f'/api/v1/comparisons/{plan["id"]}/review', json=envelope(packet, doc))
    assert response.status_code == 201, response.text
    ref = response.json()['case_analyses'][0]['content']['explanation']['stages'][0]['evidence'][0]
    assert ref['event_id'] == 41 and ref['model_reply'] == 2 and ref['start_line'] == 4
    assert (folder / 'events.jsonl').read_bytes() == raw


def test_line_reference_previews_the_exact_record_when_event_ids_repeat(comparison_env):
    import hashlib
    client, folder, _ = comparison_env
    records = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
    records.append({'type': 'tool_result', 'event_id': 2, 'ok': True,
                    'data': 'second segment result', 'files': {'huge-inventory': 'not-narrative'}})
    raw = ''.join(json.dumps(row) + '\n' for row in records).encode()
    (folder / 'events.jsonl').write_bytes(raw)
    descriptor = {'path': 'events.jsonl', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    run = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    run['cases'][0]['files'] = [descriptor]
    (folder / 'run.json').write_text(json.dumps(run), encoding='utf-8')
    (folder / 'manifest.json').write_text(json.dumps({'files': [descriptor]}), encoding='utf-8')
    plan = create(comparison_env)
    packet = prepare(client, plan['id'])
    doc = explained_document()
    doc['case_explanations'][0]['stages'][0]['evidence'] = [
        {'side': 'baseline', 'path': 'events.jsonl', 'start_line': 3, 'line_count': 1}]
    response = client.post(f'/api/v1/comparisons/{plan["id"]}/review', json=envelope(packet, doc))
    assert response.status_code == 201, response.text
    ref = response.json()['case_analyses'][0]['content']['explanation']['stages'][0]['evidence'][0]
    assert ref['start_line'] == 3 and 'second segment result' in ref['display_excerpt']
    assert 'huge-inventory' not in ref['display_excerpt']
    assert 'event_id' not in ref


def test_explanation_round_trip_and_frozen_history(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    packet = prepare(client, plan["id"])
    payload = envelope(packet, explained_document())
    response = client.post(base + "/review", json=payload)
    assert response.status_code == 201, response.text
    report = response.json()
    saved = report["case_analyses"][0]["content"]["explanation"]
    assert saved["focus"] == "baseline"
    assert saved["stages"][0]["evidence"][0]["event_id"] == 2
    assert "AssertionError" in saved["stages"][0]["evidence"][0]["excerpt"]
    assert saved["result"]["evidence"][0]["check_id"] == "result"
    assert report["explanation_coverage"] == {"provided": 1, "planned": 1, "case_ids": [CASE]}
    assert client.post(base + "/review", json=payload).json()["id"] == report["id"]
    assert client.get(base + f"/cases/{CASE}").json()["latest_analysis"]["content"]["explanation"] == saved
    assert client.get(base + "/reports/" + report["id"]).json()["case_analyses"][0]["content"]["explanation"] == saved
    assert report["metric_report"]["quality"] == packet["metric_report"]["quality"]
    # A later report may omit narration; the earlier report remains complete and frozen.
    next_packet = prepare(client, plan["id"])
    next_doc = document(); next_doc["summary"] = "只提交统计，不提供过程讲解。"
    later = client.post(base + "/review", json=envelope(next_packet, next_doc))
    assert later.status_code == 201, later.text
    assert later.json()["explanation_coverage"]["provided"] == 0
    assert "explanation" not in later.json()["case_analyses"][0]["content"]
    assert client.get(base + "/reports/" + report["id"]).json()["case_analyses"][0]["content"]["explanation"] == saved


@pytest.mark.parametrize("change", ["missing_event", "wrong_focus", "missing_check", "wrong_case", "ambiguous_locator", "duplicate_case"])
def test_bad_explanations_reject_atomically(comparison_env, change):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    doc = explained_document(); item = doc["case_explanations"][0]
    if change == "missing_event": item["stages"][0]["evidence"][0]["event_id"] = 999
    if change == "wrong_focus": item["focus"] = "candidate"
    if change == "missing_check": item["result"]["evidence"][0]["check_id"] = "nonexistent"
    if change == "wrong_case": item["case_id"] = "outside-plan"
    if change == "ambiguous_locator": item["stages"][0]["evidence"][0]["check_id"] = "result"
    if change == "duplicate_case": doc["case_explanations"].append(deepcopy(item))
    response = client.post(f"/api/v1/comparisons/{plan['id']}/review", json=envelope(packet, doc))
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/comparisons/{plan['id']}").json()["progress"]["received"] == 0


def test_empty_optional_explanations_keep_legacy_request_identity(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    old = envelope(packet, document())
    new = envelope(packet, {**document(), "case_explanations": []})
    assert old == new
    response = client.post(f"/api/v1/comparisons/{plan['id']}/review", json=old)
    assert response.status_code == 201, response.text
    from lab.db import connect
    with connect(client.app.state.db_path) as conn:
        row = conn.execute("SELECT request_hash FROM comparison_reports WHERE id=?", (response.json()["id"],)).fetchone()
        legacy_normalized = deepcopy(old)
        legacy_normalized["analysis"].setdefault("limitations", [])
        assert row["request_hash"] == digest(legacy_normalized)


def test_main_skill_payload_is_normalized_by_the_actual_api(comparison_env):
    from pathlib import Path
    from lab.skills import SkillContent
    root = Path(__file__).parents[2]
    entry = next(e for e in json.loads((root / "skills/catalog.json").read_text(encoding="utf-8"))["skills"]
                 if e["slug"] == "agent-version-comparison-workflow")
    assert all(e["slug"] != "explain-agent-runs" for e in json.loads((root / "skills/catalog.json").read_text(encoding="utf-8"))["skills"])
    payload = json.loads((root / "skills" / entry["payload_file"]).read_text(encoding="utf-8"))
    normalized = SkillContent.model_validate(payload).content
    assert normalized == payload["content"]
    assert entry["characters"] == len(normalized)
    assert entry["platform_content_hash"] == digest({"content": normalized})
    client = comparison_env[0]
    skill = client.post("/api/v1/skills", json=entry["catalog"]).json()
    saved = client.post(f"/api/v1/skills/{skill['id']}/versions", json=payload)
    assert saved.status_code == 201, saved.text
    version = saved.json()
    assert version["content_hash"] == entry["platform_content_hash"]
    assert client.post(f"/api/v1/skills/{skill['id']}/versions/{version['id']}/publish").status_code == 200
