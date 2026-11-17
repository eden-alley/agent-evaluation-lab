"""Read-only truncation facts from hash-verified archives, including legacy logs."""
import hashlib
import json

import pytest
from test_evaluation_imports import imported

URL = '/api/v1/evaluation-runs/real-run/cases/C04/output-recovery'


def archive(imported, files, *, case_paths=None):
    client, root, run = imported
    records = []
    for path, rows in files.items():
        raw = (rows if isinstance(rows, str) else ''.join(json.dumps(e) + '\n' for e in rows)).encode()
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(raw)
        records.append({'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    run['cases'][0]['files'] = [r for r in records if case_paths is None or r['path'] in case_paths]
    (root / 'run.json').write_text(json.dumps(run), encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps({'files': records}), encoding='utf-8')
    return client, root, run


def raw_length():
    return {'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': 'partial'}}],
            'usage': {'completion_tokens': 4096}}


def test_new_events_separate_scheduled_response_complete_and_task_stop(imported):
    client, root, _ = archive(imported, {'C04/events.jsonl': [
        {'type': 'model_response', 'event_id': 2, 'run_id': 'a', 'response': raw_length()},
        {'type': 'output_truncation', 'event_id': 3, 'run_id': 'a', 'source_event_id': 2, 'tools_executed': False},
        {'type': 'output_recovery', 'event_id': 4, 'run_id': 'a', 'status': 'scheduled', 'attempt': 1,
         'mode':'raise','normal_cap':512,'recovery_cap':4096,'request_cap':4096},
        {'type': 'output_recovery', 'event_id': 6, 'run_id': 'a', 'status': 'response_complete'},
        {'type': 'final_response', 'event_id': 9, 'run_id': 'a', 'stop_reason': 'max_steps', 'text': '达到最大步数'},
    ]})
    before = (root / 'run.json').read_bytes()
    response = client.get(URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body['truncations']) == 1
    assert body['truncations'][0]['completion_tokens'] == 4096
    assert body['truncations'][0]['tools_executed'] is False
    assert body['truncations'][0]['evidence']['line'] == 1
    assert [e['status'] for e in body['recovery']] == ['scheduled', 'response_complete']
    assert body['stop']['reason'] == 'max_steps'
    assert body['task_success'] is None
    assert body['recovery'][0]['mode'] == 'raise'
    assert body['recovery'][0]['normal_cap'] == 512
    assert body['recovery'][0]['recovery_cap'] == 4096
    assert (root / 'run.json').read_bytes() == before


def test_legacy_shared_logs_filter_case_and_do_not_infer_tool_effects(imported):
    client, _, _ = archive(imported, {
        'C04/events.jsonl': [{'type': 'final_response', 'event_id': 79, 'stop_reason': 'error', 'text': 'protocol_error'}],
        'shared/requests.jsonl': [
            {'case': 'OTHER', 'kind': 'response', 'number': 168, 'body': raw_length()},
            {'case': 'C04', 'kind': 'response', 'number': 169, 'body': raw_length()}],
        'continued/requests.jsonl': [{'case': 'OTHER', 'kind': 'response', 'number': 170, 'body': raw_length()}],
    }, case_paths=['C04/events.jsonl'])
    body = client.get(URL).json()
    assert len(body['truncations']) == 1
    record = body['truncations'][0]
    assert record['evidence'] == {'path': 'shared/requests.jsonl', 'line': 2, 'request_number': 169}
    assert record['tools_executed'] is None
    assert body['recovery'] == []
    assert body['stop']['reason'] == 'error'


def test_protocol_error_and_absent_logs_are_not_proof_of_truncation(imported):
    client, _, _ = imported
    assert client.get(URL).json()['truncations'] == []
    archive(imported, {'C04/events.jsonl': [
        {'type': 'final_response', 'stop_reason': 'error', 'text': 'protocol_error'}]})
    assert client.get(URL).json()['truncations'] == []


def test_case_request_log_and_matching_event_do_not_double_count(imported):
    client, _, _ = archive(imported, {
        'C04/events.jsonl': [{'type': 'model_response', 'event_id': 2, 'response': raw_length()}],
        'C04/model-requests.jsonl': [{'case': 'C04', 'kind': 'response', 'number': 1, 'body': raw_length()}],
    })
    assert len(client.get(URL).json()['truncations']) == 1


@pytest.mark.parametrize('content', ['{bad\n', '[]\n', 'null\n'])
def test_malformed_logs_are_not_reported_as_no_truncation(imported, content):
    client, _, _ = archive(imported, {'C04/events.jsonl': content})
    assert client.get(URL).status_code == 422


def test_tampered_archive_and_stale_comparison_binding_are_rejected(imported):
    client, root, _ = archive(imported, {'C04/events.jsonl': []})
    binding = {name: hashlib.sha256((root / file).read_bytes()).hexdigest()
               for name, file in [('expected_run_hash', 'run.json'), ('expected_manifest_hash', 'manifest.json')]}
    assert client.get(URL, params=binding).status_code == 200
    assert client.get(URL, params={**binding, 'expected_run_hash': '0' * 64}).status_code == 409
    (root / 'C04/events.jsonl').write_bytes(b'changed')
    assert client.get(URL).status_code == 409


def test_stopped_recovery_is_preserved_without_becoming_success(imported):
    client, _, _ = archive(imported, {'C04/events.jsonl': [
        {'type': 'model_response', 'event_id': 2, 'response': raw_length()},
        {'type': 'output_recovery', 'event_id': 3, 'status': 'stopped', 'reason': 'usage_unknown'},
        {'type': 'final_response', 'event_id': 4, 'stop_reason': 'usage_unknown', 'text': '用量未知'},
    ]})
    body = client.get(URL).json()
    assert body['recovery'][0]['reason'] == 'usage_unknown'
    assert body['task_success'] is None


def test_missing_source_ids_cannot_prove_tools_were_not_executed(imported):
    client, _, _ = archive(imported, {'C04/events.jsonl': [
        {'type': 'model_response', 'response': raw_length()},
        {'type': 'output_truncation', 'tools_executed': False},
    ]})
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()['truncations'][0]['tools_executed'] is None


@pytest.mark.parametrize('event', [
    {'type': 'output_truncation', 'run_id': [], 'source_event_id': 2, 'tools_executed': False},
    {'type': 'final_response', 'text': {'bad': 'React child'}, 'stop_reason': 'error'},
    {'type': 'output_recovery', 'status': 'stopped', 'reason': []},
    {'type': 'model_response', 'event_id': True, 'response': raw_length()},
])
def test_invalid_display_and_link_fields_return_invalid_trace(imported, event):
    client, _, _ = archive(imported, {'C04/events.jsonl': [event]})
    response = client.get(URL)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'INVALID_TRACE'
