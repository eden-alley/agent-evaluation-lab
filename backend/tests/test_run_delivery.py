"""Isolated delivery state and immutable machine-statistics contracts."""
import json

from lab.comparisons import metrics, repetition, review
from lab.db import connect
from test_comparisons import comparison_env, create


def saved_snapshot(client, identity):
    with connect(client.app.state.db_path) as conn:
        return conn.execute("SELECT snapshot FROM comparisons WHERE id=?", (identity,)).fetchone()[0]


def test_statistics_visible_before_report(comparison_env):
    client, _, config = comparison_env
    result = create(comparison_env)
    frozen = json.loads(saved_snapshot(client, result['id']))['metrics_snapshot']
    assert result['latest_report'] is None
    assert result['analysis_state'] == 'analysis_pending'
    assert result['metric_report']['registry_version'] == frozen['registry_version']
    assert result['metric_report']['conditions'] == frozen['conditions']
    assert frozen['registry_hash'] and frozen['process_hash'] and frozen['snapshot_hash']
    assert frozen['process_version'] == repetition.VERSION
    assert result['workflow'] == config['workflow']
    assert create(comparison_env)['metrics_snapshot'] == result['metrics_snapshot']


def test_statistics_and_packet_use_frozen_registry(comparison_env, monkeypatch):
    client, _, config = comparison_env
    result = create(comparison_env)
    url = f"/api/v1/comparisons/{result['id']}"
    original = client.get(url + '/review-materials').json()
    sid = config['workflow']['skill_id']
    newer = client.post(f'/api/v1/skills/{sid}/versions', json={'content': 'new active method'}).json()
    assert client.post(f'/api/v1/skills/{sid}/versions/{newer["id"]}/publish').status_code == 200
    monkeypatch.setattr(metrics, 'VERSION', 'runtime-upgrade')
    monkeypatch.setattr(repetition, 'VERSION', 'process-upgrade')
    monkeypatch.setattr(metrics, 'aggregate', lambda _: (_ for _ in ()).throw(AssertionError('must not recompute')))
    again = client.get(url + '/review-materials')
    assert again.status_code == 200, again.text
    assert again.json()['workflow'] == config['workflow']
    assert again.json()['packet_hash'] == original['packet_hash']
    assert again.json()['metric_report'] == original['metric_report']
    provided = client.post(url + '/review-materials', json={})
    assert provided.status_code == 201, provided.text
    assert provided.json()['workflow'] == config['workflow']
    assert client.get(url).json()['analysis_state'] == 'analysis_pending'
    assert client.get(url).json()['metric_report'] == result['metric_report']
    response = client.post(url + '/review', json=review.submission(original, {'summary': 'Fixed saved statistics.', 'recommendations': []}))
    assert response.status_code == 201, response.text
    assert response.json()['metric_report']['registry_version'] == original['metric_report']['registry_version']


def test_history_is_not_recomputed_on_get(comparison_env, monkeypatch):
    client, _, _ = comparison_env
    result = create(comparison_env)
    legacy = json.loads(saved_snapshot(client, result['id']))
    legacy.pop('metrics_snapshot')
    with connect(client.app.state.db_path) as conn:
        conn.execute('UPDATE comparisons SET snapshot=? WHERE id=?', (json.dumps(legacy), result['id']))
    before = saved_snapshot(client, result['id'])
    monkeypatch.setattr(metrics, 'aggregate', lambda _: (_ for _ in ()).throw(AssertionError('GET must not calculate old metrics')))
    response = client.get(f"/api/v1/comparisons/{result['id']}")
    assert response.status_code == 200, response.text
    assert response.json()['metric_report'] is None
    assert response.json()['analysis_state'] == 'analysis_pending'
    assert saved_snapshot(client, result['id']) == before


def test_run_links_pending_and_received_analysis_and_keeps_report_metrics(comparison_env, monkeypatch):
    client, _, _ = comparison_env
    first = create(comparison_env)
    second = create(comparison_env, request_id='comparison-2', name='another baseline choice')
    run = client.get('/api/v1/evaluation-runs/baseline').json()
    assert {c['id'] for c in run['comparisons']} == {first['id'], second['id']}
    assert all(c['analysis_state'] == 'analysis_pending' for c in run['comparisons'])
    url = f"/api/v1/comparisons/{first['id']}"
    packet = client.get(url + '/review-materials').json()
    report = client.post(url + '/review', json=review.submission(packet, {'summary': 'No supported advice.', 'recommendations': []}))
    assert report.status_code == 201, report.text
    report = report.json()
    monkeypatch.setattr(metrics, 'VERSION', 'new-runtime-version')
    monkeypatch.setattr(metrics, 'aggregate', lambda _: (_ for _ in ()).throw(AssertionError('read only')))
    detail = client.get(url).json()
    assert detail['analysis_state'] == 'report_received'
    assert detail['latest_report']['metric_report'] == report['metric_report']
    assert detail['latest_report']['recommendations'] == []
    assert client.get(url + '/reports/' + report['id']).json()['metric_report'] == report['metric_report']
    linked = {c['id']: c for c in client.get('/api/v1/evaluation-runs/baseline').json()['comparisons']}
    assert linked[first['id']]['analysis_state'] == 'report_received'
    assert linked[first['id']]['latest_report_id'] == report['id']
    assert linked[second['id']]['analysis_state'] == 'analysis_pending'
    assert 'comparisons' not in json.loads((comparison_env[1] / 'run.json').read_text(encoding='utf-8'))
