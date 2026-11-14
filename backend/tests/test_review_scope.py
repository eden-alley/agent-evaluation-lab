"""A batch's declared purpose, not its size alone, permits development advice."""
from copy import deepcopy
import json
import shutil

import pytest
from lab.comparisons import review
from test_comparisons import comparison_env, create, CASE
from test_skill_delivery import prepare_delivery, complete_document


def scoped(env, count):
    client, folder, config = env
    sid = config['workflow']['skill_id']
    version = client.post(f'/api/v1/skills/{sid}/versions', json={
        'content': '---\nname: comparison\nmetadata:\n  version: 0.9.0\n---\nFormal batches may include evidence-backed advice.'}).json()
    assert client.post(f'/api/v1/skills/{sid}/versions/{version["id"]}/publish').status_code == 200
    path = folder/'run.json'
    run = json.loads(path.read_text(encoding='utf-8'))
    original = run['cases'][0]
    cases = [deepcopy(original) for _ in range(count)]
    for n, case in enumerate(cases):
        case['id'] = CASE if n == 0 else f'case-{n+1}'
        case['core_acceptance'] = 'fail'
    run['cases'] = cases
    path.write_text(json.dumps(run, ensure_ascii=False), encoding='utf-8')
    candidate = folder.parent/'candidate'
    shutil.copytree(folder, candidate)
    run['id'] = 'candidate'
    (candidate/'run.json').write_text(json.dumps(run, ensure_ascii=False), encoding='utf-8')
    identity = create(env, case_ids=[c['id'] for c in cases], candidate={'kind': 'run', 'run_id': 'candidate'})['id']
    return client, identity


@pytest.mark.parametrize('count', [1, 2, 3])
def test_small_runs_cannot_request_advice_even_if_marked_formal(comparison_env, count):
    client, identity = scoped(comparison_env, count)
    packet = prepare_delivery(client, identity, review_scope='formal_batch')
    assert packet['review_policy']['mode'] == 'focused'
    assert packet['review_policy']['case_count'] == count
    assert packet['review_policy']['recommendations_allowed'] is False
    url = f'/api/v1/comparisons/{identity}/review'
    doc = complete_document()
    bad = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert bad.status_code == 422 and bad.json()['error']['code'] == 'ADVICE_OUTSIDE_REVIEW_SCOPE'
    assert client.get(f'/api/v1/comparisons/{identity}').json()['progress']['received'] == 0
    doc['recommendations'] = []
    ok = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert ok.status_code == 201, ok.text
    assert ok.json()['review_policy'] == packet['review_policy']
    assert not ok.json()['recommendations']
    assert 'no_recommendation_reason' not in ok.json()


def test_twenty_cases_are_focused_until_the_batch_is_explicitly_formal(comparison_env):
    client, identity = scoped(comparison_env, 20)
    packet = prepare_delivery(client, identity)
    assert packet['review_policy']['mode'] == 'focused'
    doc = complete_document(); doc['recommendations'][0]['priority_reason'] = '保护已有交付成果。'
    url = f'/api/v1/comparisons/{identity}/review'
    assert client.post(url, json=review.submission(packet, doc)).status_code == 422
    packet = prepare_delivery(client, identity, review_scope='formal_batch')
    assert packet['review_policy']['mode'] == 'formal_batch'
    assert review.analyst_materials(packet)['review_policy'] == packet['review_policy']
    response = client.post(url, json=review.submission(packet, doc, 'offline_program'))
    assert response.status_code == 201, response.text
    report = response.json()
    assert len(report['recommendations']) == 1 and report['review_policy']['case_count'] == 20
    assert client.post(url, json=review.submission(packet, doc, 'offline_program')).json()['id'] == report['id']
    # A formal batch also accepts no new advice; there is no compulsory reason field.
    later = prepare_delivery(client, identity, review_scope='formal_batch')
    doc.pop('recommendations')
    result = client.post(url, json=review.submission(later, doc, 'offline_program'))
    assert result.status_code == 201, result.text
    assert result.json()['recommendations'] == []
    assert client.get(f'/api/v1/comparisons/{identity}/reports/{report["id"]}').json()['report_hash'] == report['report_hash']


def test_new_method_cannot_bypass_pinned_scope_by_omitting_delivery(comparison_env):
    client, identity = scoped(comparison_env, 20)
    packet = prepare_delivery(client, identity, review_scope='formal_batch')
    packet.pop('delivery_id')
    response = client.post(f'/api/v1/comparisons/{identity}/review', json=review.submission(packet, complete_document()))
    assert response.status_code == 422 and response.json()['error']['code'] == 'METHOD_DELIVERY_REQUIRED'
