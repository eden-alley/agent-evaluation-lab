"""Key-case review is selective explanation, never selective measurement."""
from copy import deepcopy
from types import SimpleNamespace
import json
import shutil

from lab.comparisons import delivery, metrics, review
from lab.db import connect
from test_capability_review import sample
from test_comparisons import comparison_env, create, CASE
from test_skill_delivery import complete_document, prepare_delivery


def seven(env):
    client, folder, config = env
    sid = config['workflow']['skill_id']
    version = client.post(f'/api/v1/skills/{sid}/versions', json={
        'content': '---\nname: comparison\nmetadata:\n  version: 0.7.0\n---\nReview key cases and prioritize evidence-backed actions.',
        'change_note': 'key-case fixture'}).json()
    assert client.post(f'/api/v1/skills/{sid}/versions/{version["id"]}/publish').status_code == 200
    candidate = folder.parent / 'candidate'
    shutil.copytree(folder, candidate)
    run = json.loads((candidate / 'run.json').read_text(encoding='utf-8'))
    run['id'] = 'candidate'
    run['cases'][0]['core_acceptance'] = 'fail'
    (candidate / 'run.json').write_text(json.dumps(run), encoding='utf-8')
    identity = create(env, candidate={'kind': 'run', 'run_id': 'candidate'})['id']
    return client, identity, prepare_delivery(client, identity)


def test_candidates_keep_regressions_unknown_and_repetition_but_not_every_resource_increase():
    from lab.comparisons.key_cases import candidates
    table = metrics.aggregate(sample())
    # A successful case with more requests is a resource observation, not a failure.
    table['cases'][2]['candidate']['metrics']['model_requests'] = 100
    table['cases'][0]['candidate']['core_acceptance'] = 'unknown'
    rows = candidates(table)
    assert [r['case_id'] for r in rows] == ['one', 'two']
    assert any('不确定' in reason for reason in rows[0]['reasons'])
    assert any('退步' in reason for reason in rows[1]['reasons'])
    table['repetition']['cases'] = [{'case_id': 'three', 'comparable': True,
        'baseline': {'useless': 0}, 'candidate': {'useless': 1}}]
    assert [r['case_id'] for r in candidates(table)] == ['one', 'two', 'three']


def test_baseline_diagnosis_does_not_make_every_healthy_case_an_anomaly():
    from lab.comparisons.key_cases import candidates
    snapshot = sample(); snapshot['candidate'] = None
    assert [r['case_id'] for r in candidates(metrics.aggregate(snapshot))] == ['one']


def test_seven_does_not_require_all_candidates_and_advice_needs_explanation(comparison_env):
    client, identity, packet = seven(comparison_env)
    req = packet['skill_delivery']['requirements']
    assert req['explanation_policy'] == 'key_cases'
    assert req['explanation_case_ids'] == []
    assert req['advice_case_explanations_required'] is True
    assert packet['key_case_candidates']
    # Preparing more cases creates candidates, not mandatory full-suite narratives.
    with connect(client.app.state.db_path) as conn:
        two = deepcopy(packet)
        another = deepcopy(two['metric_report']['cases'][0]); another['case_id'] = 'another-case'
        two['metric_report']['cases'].append(another)
        issued = delivery.issue(conn, SimpleNamespace(headers={}), identity, two)
    assert issued['skill_delivery']['requirements']['explanation_case_ids'] == []
    assert len(issued['key_case_candidates']) == 2
    doc = complete_document()
    doc['recommendations'][0]['priority_reason'] = '优先保护已完成的功能成果。'
    url = f'/api/v1/comparisons/{identity}/review'
    missing = deepcopy(doc); missing.pop('case_explanations')
    assert client.post(url, json=review.submission(packet, missing, 'offline_program')).status_code == 422
    assert client.get(f'/api/v1/comparisons/{identity}').json()['progress']['received'] == 0
    # Optional diagnostic fields no longer need boilerplate in the analyst document.
    for key in ('known_mechanism', 'cause_status', 'cause', 'success_signals', 'guardrails'):
        doc['recommendations'][0].pop(key, None)
    response = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert response.status_code == 201, response.text
    report = response.json()
    assert report['explanation_coverage']['mode'] == 'key_cases'
    assert report['explanation_coverage']['total_cases'] == 1
    assert report['explanation_coverage']['provided'] == 1
    assert report['recommendations'][0]['cause_status'] == 'unresolved'


def test_seven_allows_statistics_without_forced_narration_and_records_unexpanded_candidates(comparison_env):
    client, identity, packet = seven(comparison_env)
    doc = {'summary': '原判与指标全量保留。', 'recommendations': [],
           'no_recommendation_reason': '现有证据不足以提出可靠动作，异常题尚未展开。'}
    result = client.post(f'/api/v1/comparisons/{identity}/review', json=review.submission(packet, doc, 'offline_program'))
    assert result.status_code == 201, result.text
    report = result.json()
    assert report['progress']['received'] == 1
    assert report['explanation_coverage']['provided'] == 0
    assert report['explanation_coverage']['unexpanded_candidate_case_ids'] == [CASE]
    assert report['case_analyses'][0]['content']['observations']


def test_key_only_check_rejects_unrelated_narration_unless_explicitly_requested(comparison_env):
    from lab.comparisons.review_schemas import ReviewSubmission
    from lab.datasets import QualityError
    import pytest
    client, identity, packet = seven(comparison_env)
    with connect(client.app.state.db_path) as conn:
        clear = deepcopy(packet)
        for side in ('baseline', 'candidate'):
            clear['metric_report']['cases'][0][side]['core_acceptance'] = 'pass'
        for metric in clear['metric_report']['quality']:
            metric['regressed_cases'] = []
        clear['metric_report']['repetition']['cases'] = []
        issued = delivery.issue(conn, SimpleNamespace(headers={}), identity, clear)
        doc = complete_document(); doc['recommendations'] = []
        doc['no_recommendation_reason'] = '没有可靠动作。'
        payload = ReviewSubmission.model_validate(review.submission(issued, doc, 'offline_program'))
        with pytest.raises(QualityError, match='关键题'):
            delivery.validate(conn, identity, clear, payload)
        explicit = delivery.issue(conn, SimpleNamespace(headers={}), identity, clear, [CASE])
        payload = ReviewSubmission.model_validate(review.submission(explicit, doc, 'offline_program'))
        assert delivery.validate(conn, identity, clear, payload)
