"""Offline review contract: derived statistics are not new task grades."""
from copy import deepcopy
import json

import pytest
from lab.comparisons import metrics, review
from lab.db import connect
from test_comparisons import comparison_env, create, CASE


def sample():
    def side(values):
        return {"cases": {cid: {"case": {"id": cid, "title": cid,
            "task": {"turns": ["fixed task"]}, "core_acceptance": "pass" if value else "fail",
            "checks": [{"id": "scope", "rule": "protect files", "value": value, "required_for_task": True}]},
            "metrics": {"model_requests": 10}, "materials": []} for cid, value in values.items()}}
    return {"case_ids": ["one", "two", "three"],
            "baseline": side({"one": 0, "two": 1, "three": 1}),
            "candidate": side({"one": 1, "two": 0, "three": 1}), "is_simulation": False}


def test_registry_keeps_gains_and_losses_and_explicit_unknown_dimensions():
    table = metrics.aggregate(sample())
    scope = next(m for m in table["quality"] if m["id"] == "scope")
    assert (scope["before"], scope["after"], scope["paired_cases"]) == (2, 2, 3)
    assert scope["direction"] == "mixed"
    assert scope["improved_cases"] == ["one"] and scope["regressed_cases"] == ["two"]
    assert {m["id"] for m in table["unassessed"]} >= {"context_quality", "useless_repetition", "conciseness", "recovery_quality"}
    assert table["coverage"]["unassessed"] >= 4


def test_missing_rule_invalid_check_and_changed_task_are_not_zeroes():
    snap = sample()
    snap["candidate"]["cases"]["one"]["case"]["checks"][0]["rule"] = "different rule"
    snap["candidate"]["cases"]["two"]["case"]["checks"][0]["invalid"] = True
    snap["candidate"]["cases"]["three"]["case"]["task"] = {"turns": ["different task"]}
    table = metrics.aggregate(snap)
    scope = next(m for m in table["quality"] if m["id"] == "scope")
    assert scope["paired_cases"] == 0 and scope["direction"] == "insufficient"
    assert len(scope["excluded"]) == 3
    completion = next(m for m in table["quality"] if m["id"] == "completion")
    assert "one" in [e["case_id"] for e in completion["excluded"]]
    snap["candidate"] = None
    table = metrics.aggregate(snap)
    assert all(m["paired_cases"] == 0 for m in table["quality"])
    assert table["cases"][0]["baseline"]["core_acceptance"] in ("pass", "fail")


def document():
    return {"summary": "离线验证材料统计与一次提交。",
        "recommendations": [{"title": "先核对请求消耗", "metric_id": "model_requests", "case_ids": [CASE],
            "known_mechanism": "已有归档请求计数。", "gap": "计数变化尚不能说明调用是否多余。",
            "cause_status": "hypothesis", "cause": "先核对预算和任务完成程度。",
            "action": "只读检查相同任务的请求轨迹。", "validation": "固定任务与请求上限后比较。",
            "success_signals": "任务结果不退步，减少已确认无信息增益的调用。",
            "guardrails": "不因为调用减少就判为能力提高。"}]}


def prepare(client, identity):
    response = client.get(f"/api/v1/comparisons/{identity}/review-materials")
    assert response.status_code == 200, response.text
    return response.json()


def envelope(packet, analysis=None):
    return review.submission(packet, analysis or document(), origin="offline_program")


def test_one_submission_is_atomic_idempotent_and_keeps_packet_identity(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    url = f"/api/v1/comparisons/{plan['id']}/review"
    payload = envelope(packet)
    result = client.post(url, json=payload)
    assert result.status_code == 201, result.text
    report = result.json()
    assert report["metric_report"]["registry_version"] == metrics.VERSION
    assert report["analysis_origin"]["kind"] == "offline_program"
    assert report["progress"]["received"] == 1
    retry = client.post(url, json=payload)
    assert retry.status_code == 201 and retry.json()["id"] == report["id"]
    assert prepare(client, plan["id"])["packet_hash"] == packet["packet_hash"]
    conflict = deepcopy(payload)
    conflict["analysis"]["summary"] += "changed"
    assert client.post(url, json=conflict).status_code == 409
    changed = deepcopy(document()); changed["summary"] += " another analysis"
    assert client.post(url, json=envelope(packet, changed)).status_code == 409


def test_invalid_advice_rolls_back_and_does_not_revise_cases(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    bad = document(); bad["recommendations"][0]["case_ids"] = ["not-in-plan"]
    result = client.post(f"/api/v1/comparisons/{plan['id']}/review", json=envelope(packet, bad))
    assert result.status_code == 422, result.text
    assert client.get(f"/api/v1/comparisons/{plan['id']}").json()["progress"]["received"] == 0


def test_mid_batch_error_rolls_back_all_rows(comparison_env, monkeypatch):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    from lab.comparisons import service
    original = service.submit_case
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        from lab.datasets import QualityError
        raise QualityError("TEST_ROLLBACK", "rollback fixture", 422)
    monkeypatch.setattr(service, "submit_case", fail_after_write)
    result = client.post(f"/api/v1/comparisons/{plan['id']}/review", json=envelope(packet))
    assert result.status_code == 422
    assert client.get(f"/api/v1/comparisons/{plan['id']}").json()["progress"]["received"] == 0


def test_source_drift_rejects_new_submission_but_saved_receipt_remains_readable(comparison_env):
    client, folder, _ = comparison_env
    plan = create(comparison_env)
    packet = prepare(client, plan["id"])
    (folder / "events.jsonl").write_text("changed", encoding="utf-8")
    result = client.post(f"/api/v1/comparisons/{plan['id']}/review", json=envelope(packet))
    assert result.status_code == 409, result.text
    assert client.get(f"/api/v1/comparisons/{plan['id']}").json()["progress"]["received"] == 0


def test_friendly_material_reader_resolves_path_and_never_accepts_ambiguous_alias(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    url = f"/api/v1/comparisons/{plan['id']}/review-material"
    result = client.get(url, params={"case_id": CASE, "side": "baseline", "path": "events.jsonl", "line_count": 5})
    assert result.status_code == 200 and "AssertionError" in result.json()["excerpt"]
    assert client.get(url, params={"case_id": CASE, "side": "baseline", "path": "../run.json"}).status_code == 404
    listing = client.get(f"/api/v1/comparisons/{plan['id']}/review-catalog", params={"case_id": CASE, "side": "baseline", "query": "events"}).json()
    assert listing["total"] == 1 and listing["items"][0]["path"] == "events.jsonl"


def test_analyst_summary_excludes_machine_envelope_and_large_catalog(comparison_env):
    packet = prepare(comparison_env[0], create(comparison_env)["id"])
    brief = review.analyst_materials(packet)
    assert "packet_hash" not in brief and "case_revisions" not in brief
    assert all("case_evidence" not in m for m in brief["metric_report"]["quality"])
    assert brief["cases"][0]["case_id"] == CASE
