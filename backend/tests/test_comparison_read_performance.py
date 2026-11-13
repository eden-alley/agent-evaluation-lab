"""Historical reads stay cheap; source checks remain strict and request-scoped."""
import os
import sqlite3
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from lab.main import create_app
from lab.comparisons import materials
from test_comparisons import (
    CASE, analysis_payload, case_materials, comparison_env, create, final_payload,
)


def saved_report(env):
    client = env[0]
    plan = create(env)
    base = f"/api/v1/comparisons/{plan['id']}"
    payload = analysis_payload(case_materials(env, plan))
    analysis = client.post(base + f"/cases/{CASE}/analyses", json=payload)
    assert analysis.status_code == 201, analysis.text
    report = client.post(base + "/reports", json=final_payload(analysis.json()))
    assert report.status_code == 201, report.text
    return plan, payload, report.json()


def test_historical_list_detail_case_and_report_do_not_scan_originals(comparison_env):
    client, _, _ = comparison_env
    plan, _, report = saved_report(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    with patch.object(materials, "source_state", side_effect=AssertionError("history must not rescan originals")):
        listing = client.get("/api/v1/comparisons")
        detail = client.get(base)
        case = client.get(base + f"/cases/{CASE}")
        history = client.get(base + "/reports/" + report["id"])
    assert all(r.status_code == 200 for r in (listing, detail, case, history))
    assert "latest_report" not in listing.json()["items"][0]
    assert "queue" not in listing.json()["items"][0]
    assert history.json()["report_hash"] == report["report_hash"]
    for value in (listing.json()["items"][0], detail.json(), case.json(), history.json()):
        assert value["source_state_scope"] == "last_full_verification"
        assert value["source_checked_at"]


def test_explicit_check_persists_real_time_and_detects_same_size_same_mtime_change(comparison_env):
    client, folder, _ = comparison_env
    plan, payload, report = saved_report(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    initial = client.get(base).json()
    assert initial.get("source_checked_at"), "a completed source check must record its real time"
    trace = folder / "events.jsonl"
    original, stat = trace.read_bytes(), trace.stat()
    trace.write_bytes(original.replace(b"AssertionError: 0", b"AssertionError: 1"))
    os.utime(trace, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    historical = client.get(base).json()
    assert historical["source_checked_at"] == initial["source_checked_at"]
    assert historical["source_state"] == "unchanged"  # previous check, explicitly scoped as historical
    checked = client.post(base + "/verify")
    assert checked.status_code == 200, checked.text
    assert checked.json()["source_state"] == "changed"
    assert checked.json()["source_checked_at"] >= initial["source_checked_at"]
    archived = next(m for m in case_materials(comparison_env, plan)["baseline"]["materials"] if m["kind"] == "archive")
    assert client.get(base + f"/cases/{CASE}/materials/{archived['id']}").status_code == 409
    assert client.post(base + f"/cases/{CASE}/analyses", json={**payload, "request_id": "changed", "revision": 1}).status_code == 409
    assert client.get(base).json()["source_state"] == "changed"
    assert client.get(base + "/reports/" + report["id"]).json()["report_hash"] == report["report_hash"]
    trace.write_bytes(original)
    checked = client.post(base + "/verify")
    assert checked.status_code == 200 and checked.json()["source_state"] == "unchanged"
    with TestClient(create_app(folder.parent.parent / "lab.sqlite3")) as reopened:
        assert reopened.get(base).json()["source_checked_at"] == checked.json()["source_checked_at"]


def test_new_analysis_checks_once_and_never_reuses_check_between_requests(comparison_env):
    client, folder, _ = comparison_env
    plan = create(comparison_env)
    payload = analysis_payload(case_materials(comparison_env, plan))
    base = f"/api/v1/comparisons/{plan['id']}"
    original_read = Path.read_bytes
    reads = Counter()

    def tracked_read(path):
        reads[str(path)] += 1
        return original_read(path)

    with patch.object(Path, "read_bytes", tracked_read):
        response = client.post(base + f"/cases/{CASE}/analyses", json=payload)
    assert response.status_code == 201, response.text
    assert reads[str(folder / "events.jsonl")] == 1, "multiple embedded refs must share one full check in this request"
    (folder / "events.jsonl").write_text("changed after previous request", encoding="utf-8")
    response = client.post(base + f"/cases/{CASE}/analyses", json={**payload, "request_id": "next", "revision": 1})
    assert response.status_code == 409, response.text
    assert client.get(base).json()["source_state"] == "changed"
    embedded = case_materials(comparison_env, plan)["candidate"]["materials"][0]
    assert client.get(base + f"/cases/{CASE}/materials/{embedded['id']}").status_code == 409


@pytest.mark.parametrize("changed", ["run.json", "manifest.json", "events.jsonl", "missing"])
def test_drift_blocks_raw_reads_new_analyses_and_new_final_reports(comparison_env, changed):
    client, folder, _ = comparison_env
    plan, payload, report = saved_report(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    embedded = case_materials(comparison_env, plan)["baseline"]["materials"][0]
    if changed == "missing":
        (folder / "events.jsonl").unlink()
    else:
        (folder / changed).write_text("changed", encoding="utf-8")
    assert client.get(base + f"/cases/{CASE}/materials/{embedded['id']}").status_code == 409
    assert client.post(base + f"/cases/{CASE}/analyses", json={**payload, "request_id": "next", "revision": 1}).status_code == 409
    final = {**final_payload({"id": report["case_report_ids"][0]}), "request_id": "new-final"}
    assert client.post(base + "/reports", json=final).status_code == 409
    assert client.get(base).json()["source_state"] == "changed"
    assert client.get(base + "/reports/" + report["id"]).status_code == 200


def test_version6_upgrade_keeps_immutable_reports_and_marks_unrecorded_time(comparison_env):
    client, folder, _ = comparison_env
    plan, _, report = saved_report(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    assert "source_checked_at" in client.get(base).json()
    db = folder.parent.parent / "lab.sqlite3"
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT snapshot FROM comparisons WHERE id=?", (plan["id"],)).fetchone()[0]
        content = conn.execute("SELECT content FROM comparison_reports WHERE id=?", (report["id"],)).fetchone()[0]
        conn.execute("DROP TABLE comparison_source_checks")
        conn.execute("PRAGMA user_version=6")
    with TestClient(create_app(db)) as upgraded:
        value = upgraded.get(base).json()
        assert value["source_state"] == "unchecked" and value["source_checked_at"] is None
        assert value["latest_report"]["report_hash"] == report["report_hash"]
        with sqlite3.connect(db) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
            assert conn.execute("SELECT snapshot FROM comparisons WHERE id=?", (plan["id"],)).fetchone()[0] == before
            assert conn.execute("SELECT content FROM comparison_reports WHERE id=?", (report["id"],)).fetchone()[0] == content
        result = upgraded.post(base + "/verify")
        assert result.status_code == 200 and result.json()["source_checked_at"]


def test_late_recording_of_an_older_check_cannot_replace_more_recent_status(comparison_env):
    client, _, _ = comparison_env
    plan = create(comparison_env)
    base = f"/api/v1/comparisons/{plan['id']}"
    latest = client.get(base).json()
    with patch("lab.comparisons.service.now", return_value="2000-01-01T00:00:00+00:00"), \
            patch.object(materials, "source_state", return_value="changed"):
        assert client.post(base + "/verify").status_code == 200
    value = client.get(base).json()
    assert value["source_checked_at"] == latest["source_checked_at"]
    assert value["source_state"] == latest["source_state"]
