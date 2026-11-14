"""A real-run page reuses a matching saved explanation, never a different trial."""
from copy import deepcopy
import json

from test_comparisons import comparison_env, create, CASE
from test_capability_review import prepare, envelope, document
from test_case_explanations import explained_document


def saved(env, doc=None):
    client, _, _ = env
    identity = create(env)['id']
    response = client.post(f'/api/v1/comparisons/{identity}/review',
                           json=envelope(prepare(client, identity), doc or explained_document()))
    assert response.status_code == 201, response.text
    return identity, response.json()


def endpoint(): return f'/api/v1/evaluation-runs/baseline/cases/{CASE}/explanation'


def test_real_run_reuses_saved_baseline_with_evidence_and_provenance(comparison_env):
    client, _, _ = comparison_env
    identity, report = saved(comparison_env)
    response = client.get(endpoint())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'available'
    assert body['source']['comparison_id'] == identity
    assert body['source']['report_id'] == report['id']
    assert body['source']['side'] == 'baseline'
    assert body['source']['report_is_simulation'] is True
    assert 'AssertionError' in body['explanation']['stages'][0]['evidence'][0]['excerpt']
    assert body['explanation']['focus'] == 'baseline'
    assert client.get('/api/v1/evaluation-runs/baseline').json()['cases'][0]['checks'][0]['value'] == 0


def test_latest_report_without_explanation_does_not_resurrect_old_full_narration(comparison_env):
    client, _, _ = comparison_env
    identity, _ = saved(comparison_env)
    response = client.post(f'/api/v1/comparisons/{identity}/review',
                           json=envelope(prepare(client, identity), document()))
    assert response.status_code == 201, response.text
    body = client.get(endpoint()).json()
    assert body['status'] == 'not_explained'
    assert body['explanation'] is None
    assert body['source']['report_id'] == response.json()['id']


def test_candidate_story_is_not_used_as_real_baseline_story(comparison_env):
    client, _, _ = comparison_env
    doc = explained_document(); e = doc['case_explanations'][0]
    e['focus'] = 'candidate'
    for part in [*e['stages'], e['result']]:
        part['evidence'] = [{'side': 'candidate', 'path': 'case-record.json', 'check_id': 'result'}]
    saved(comparison_env, doc)
    body = client.get(endpoint()).json()
    assert body['status'] == 'not_explained' and body['explanation'] is None


def test_unknown_run_or_case_is_not_matched_by_case_id_alone(comparison_env):
    client, _, _ = comparison_env
    saved(comparison_env)
    assert client.get(endpoint().replace('baseline', 'other-run')).status_code == 404
    assert client.get(endpoint().replace(CASE, 'other-case')).status_code == 404


def test_without_report_returns_automatic_summary_state(comparison_env):
    client, _, _ = comparison_env
    body = client.get(endpoint()).json()
    assert body['status'] == 'not_explained' and body['explanation'] is None


def test_changed_original_does_not_masquerade_as_current_explanation(comparison_env):
    client, folder, _ = comparison_env
    saved(comparison_env)
    (folder/'events.jsonl').write_text('changed after report', encoding='utf-8')
    body = client.get(endpoint()).json()
    assert body['status'] == 'source_changed' and body['explanation'] is None


def test_changed_run_record_is_detected_even_when_event_file_matches(comparison_env):
    client, folder, _ = comparison_env
    saved(comparison_env)
    data = json.loads((folder/'run.json').read_text(encoding='utf-8'))
    data['cases'][0]['task'] = {'turns': ['different task']}
    (folder/'run.json').write_text(json.dumps(data), encoding='utf-8')
    body = client.get(endpoint()).json()
    assert body['status'] == 'source_changed' and body['explanation'] is None
