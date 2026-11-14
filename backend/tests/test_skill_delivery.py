"""Method delivery is recorded input, never proof of semantic compliance."""
from copy import deepcopy

from lab.comparisons import review
from lab.db import connect
from test_comparisons import comparison_env, create, CASE
from test_case_explanations import explained_document


def prepare_delivery(client, identity, **body):
    response = client.post(f"/api/v1/comparisons/{identity}/review-materials", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def complete_document():
    doc = explained_document()
    doc["recommendations"][0]["evidence"] = [{"case_id": CASE, "side": "baseline",
        "path": "events.jsonl", "event_id": 2}]
    return doc


def publish_six(client, config):
    sid = config['workflow']['skill_id']
    version = client.post(f'/api/v1/skills/{sid}/versions', json={
        'content': '---\nname: comparison\nmetadata:\n  version: 0.6.0\n---\nExplain every selected case and prioritize evidence-backed actions.',
        'change_note': 'v0.6 fixture'}).json()
    assert client.post(f'/api/v1/skills/{sid}/versions/{version["id"]}/publish').status_code == 200


def test_six_defaults_to_all_cases_and_preserves_priority_reason(comparison_env):
    from types import SimpleNamespace
    from lab.comparisons import delivery
    client, _, config = comparison_env
    publish_six(client, config)
    identity = create(comparison_env)['id']
    packet = prepare_delivery(client, identity)
    with connect(client.app.state.db_path) as conn:
        two = deepcopy(packet)
        another = deepcopy(two['metric_report']['cases'][0]); another['case_id'] = 'another-case'
        two['metric_report']['cases'].append(another)
        issued = delivery.issue(conn, SimpleNamespace(headers={}), identity, two)
    assert issued['skill_delivery']['requirements']['explanation_case_ids'] == [CASE, 'another-case']
    doc = complete_document()
    url = f'/api/v1/comparisons/{identity}/review'
    missing = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert missing.status_code == 422
    assert client.get(f'/api/v1/comparisons/{identity}').json()['progress']['received'] == 0
    doc['recommendations'][0]['priority_reason'] = '已有功能成果因交付约束失败，应先核查交付检查。'
    result = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert result.status_code == 201, result.text
    assert result.json()['recommendations'][0]['priority_reason'] == doc['recommendations'][0]['priority_reason']


def test_delivery_returns_exact_published_text_and_frozen_report(comparison_env):
    client, _, config = comparison_env
    identity = create(comparison_env)["id"]
    packet = prepare_delivery(client, identity)
    delivery = packet["skill_delivery"]
    assert delivery["skill"]["content"] == "Read the paired evidence and report limitations."
    assert delivery["skill"]["version_id"] == config["workflow"]["version_id"]
    assert delivery["read_status"] == "not_verified"
    assert delivery["requirements"]["explanation_case_ids"] == [CASE]
    assert review.analyst_materials(packet)["skill_delivery"] == delivery
    payload = review.submission(packet, complete_document(), "offline_program")
    url = f"/api/v1/comparisons/{identity}/review"
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["skill_delivery"] == delivery
    assert report["output_checks"]["status"] == "passed"
    assert report["output_checks"]["semantic_status"] == "not_evaluated"
    evidence = report["recommendations"][0]["evidence"][0]
    assert evidence["case_id"] == CASE and evidence["event_id"] == 2
    assert "AssertionError" in evidence["excerpt"]
    assert client.post(url, json=payload).json()["id"] == report["id"]
    new = client.post(f"/api/v1/skills/{config['workflow']['skill_id']}/versions",
        json={"content": "A different method.", "change_note": "after saved report"}).json()
    client.post(f"/api/v1/skills/{config['workflow']['skill_id']}/versions/{new['id']}/publish")
    saved = client.get(f"/api/v1/comparisons/{identity}/reports/{report['id']}").json()
    assert saved["skill_delivery"]["skill"]["content"] == delivery["skill"]["content"]


def test_missing_requested_explanation_and_advice_evidence_are_atomic(comparison_env):
    client, _, _ = comparison_env
    identity = create(comparison_env)["id"]
    packet = prepare_delivery(client, identity)
    for missing in ("case_explanations", "advice_evidence"):
        doc = complete_document()
        if missing == "case_explanations": doc.pop(missing)
        else: doc["recommendations"][0].pop("evidence")
        response = client.post(f"/api/v1/comparisons/{identity}/review",
            json=review.submission(packet, doc, "offline_program"))
        assert response.status_code == 422, response.text
        assert client.get(f"/api/v1/comparisons/{identity}").json()["progress"]["received"] == 0


def test_delivery_cannot_be_used_for_another_comparison(comparison_env):
    client, _, _ = comparison_env
    first = create(comparison_env)["id"]
    second = create(comparison_env, request_id="second-plan")["id"]
    a, b = prepare_delivery(client, first), prepare_delivery(client, second)
    b["delivery_id"] = a["delivery_id"]
    response = client.post(f"/api/v1/comparisons/{second}/review",
        json=review.submission(b, complete_document(), "offline_program"))
    assert response.status_code == 422, response.text


def test_no_advice_needs_no_reason_and_invalid_evidence_is_still_rejected(comparison_env):
    client, _, _ = comparison_env
    identity = create(comparison_env)["id"]
    packet = prepare_delivery(client, identity)
    doc = complete_document(); doc["recommendations"] = []
    url = f"/api/v1/comparisons/{identity}/review"
    response = client.post(url, json=review.submission(packet, doc))
    assert response.status_code == 201, response.text
    assert response.json()['recommendations'] == []
    assert not response.json().get('no_recommendation_reason')
    assert not any(c['id'] == 'advice' for c in response.json()['output_checks']['checks'])
    packet = prepare_delivery(client, identity)
    bad = complete_document(); bad["recommendations"][0]["evidence"][0]["event_id"] = 999
    assert client.post(url, json=review.submission(packet, bad)).status_code == 422
    doc["no_recommendation_reason"] = "现有材料不足以提出可靠动作。"
    ok = client.post(url, json=review.submission(packet, doc))
    assert ok.status_code == 201, ok.text
    assert ok.json()["no_recommendation_reason"] == doc["no_recommendation_reason"]


def test_omitted_advice_and_reason_are_valid_outputs(comparison_env):
    client, _, _ = comparison_env
    identity = create(comparison_env)['id']
    packet = prepare_delivery(client, identity)
    assert packet['skill_delivery']['requirements']['no_advice_reason_required'] is False
    doc = complete_document(); doc.pop('recommendations')
    response = client.post(f'/api/v1/comparisons/{identity}/review', json=review.submission(packet, doc, 'offline_program'))
    assert response.status_code == 201, response.text
    assert response.json()['recommendations'] == []


def test_unselected_explanation_case_is_rejected_at_preparation(comparison_env):
    client, _, _ = comparison_env
    identity = create(comparison_env)["id"]
    response = client.post(f"/api/v1/comparisons/{identity}/review-materials",
        json={"explain_case_ids": ["not-in-plan"]})
    assert response.status_code == 422


def test_changed_archive_cannot_create_a_delivery_record(comparison_env):
    client, folder, _ = comparison_env
    identity = create(comparison_env)["id"]
    (folder / "events.jsonl").write_text("changed", encoding="utf-8")
    response = client.post(f"/api/v1/comparisons/{identity}/review-materials", json={})
    assert response.status_code == 409
    with connect(folder.parent.parent / "lab.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM review_preparations").fetchone()[0] == 0


def test_version7_upgrade_preserves_report_and_has_no_invented_delivery(comparison_env):
    import sqlite3
    from fastapi.testclient import TestClient
    from lab.main import create_app
    from test_capability_review import prepare, envelope
    client, folder, _ = comparison_env
    identity = create(comparison_env)["id"]
    old = client.post(f"/api/v1/comparisons/{identity}/review", json=envelope(prepare(client, identity))).json()
    db = folder.parent.parent / "lab.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE review_preparations")
        conn.execute("PRAGMA user_version=7")
    with TestClient(create_app(db)) as upgraded:
        saved = upgraded.get(f"/api/v1/comparisons/{identity}/reports/{old['id']}").json()
        assert saved["report_hash"] == old["report_hash"]
        assert "skill_delivery" not in saved
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        assert conn.execute("SELECT count(*) FROM review_preparations").fetchone()[0] == 0
