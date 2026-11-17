"""Observed output truncation/recovery facts; never change grades or infer success."""
import hashlib
import json
from collections import Counter
from pathlib import PurePosixPath

from .datasets import QualityError


def _rows(folder, path):
    from .evaluation_imports import read_artifact
    _, _, raw = read_artifact(folder, path, max_bytes=32 * 1024 * 1024)
    try:
        rows = [(i, json.loads(line)) for i, line in enumerate(raw.decode('utf-8-sig').splitlines(), 1) if line.strip()]
        if any(not isinstance(row, dict) for _, row in rows):
            raise ValueError('event must be an object')
        return rows
    except (ValueError, UnicodeError) as error:
        raise QualityError('INVALID_TRACE', '记录格式无法识别，请查看原始证据。', 422) from error


def _reference(path, line, row, *, request=False):
    ref = {'path': path, 'line': line}
    field, source = ('request_number', 'number') if request else ('event_id', 'event_id')
    if type(row.get(source)) is int:
        ref[field] = row[source]
    return ref


def _is_length(raw):
    choices = raw.get('choices') if isinstance(raw, dict) else None
    return (isinstance(choices, list) and bool(choices) and isinstance(choices[0], dict)
            and choices[0].get('finish_reason') == 'length')


def _fingerprint(raw):
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def _validate_event(event):
    if event.get('type') not in ('model_response', 'output_truncation', 'output_recovery', 'final_response'):
        return
    valid = True
    for key in ('event_id', 'source_event_id', 'attempt'):
        value = event.get(key)
        valid &= value is None or (type(value) is int and value > 0)
    phase = event.get('phase')
    valid &= phase is None or (type(phase) is int and phase >= 0)
    for key in ('run_id', 'reason', 'text', 'stop_reason'):
        valid &= event.get(key) is None or isinstance(event[key], str)
    valid &= event.get('tools_executed') is None or type(event['tools_executed']) is bool
    valid &= event.get('mode') in (None, 'raise', 'split')
    for key in ('normal_cap', 'recovery_cap', 'request_cap'):
        value = event.get(key)
        valid &= value is None or (type(value) is int and value > 0)
    if not valid:
        raise QualityError('INVALID_TRACE', '事件中的来源关联或展示字段损坏，请查看原始记录。', 422)


def summarize(folder, case):
    paths = [f['path'] for f in case.get('files', [])]
    traces = [p for p in paths if PurePosixPath(p).name == 'events.jsonl']
    if len(traces) > 1:
        raise QualityError('INVALID_TRACE', '本题包含多份事件记录，无法确定运行顺序。', 422)
    result = {'truncations': [], 'recovery': [], 'stop': None, 'task_success': None,
              'limitations': '仅展示归档中可确认的事实。完整响应不代表任务通过；未记录不等于未发生。'}
    event_bodies = set()
    for path in traces:
        rows = _rows(folder, path)
        for _, event in rows:
            _validate_event(event)
        response_ids = Counter((e.get('run_id'), e.get('phase'), e.get('event_id')) for _, e in rows
                               if e.get('type') == 'model_response' and type(e.get('event_id')) is int)
        # Pair within the same run and phase; event ids may restart each turn.
        not_executed = {(e.get('run_id'), e.get('phase'), e.get('source_event_id')) for _, e in rows
                        if e.get('type') == 'output_truncation' and e.get('tools_executed') is False
                        and type(e.get('source_event_id')) is int}
        for line, event in rows:
            evidence = _reference(path, line, event)
            if event.get('type') == 'model_response' and _is_length(raw := event.get('response')):
                event_bodies.add(_fingerprint(raw))
                count = (raw.get('usage') or {}).get('completion_tokens') if isinstance(raw.get('usage'), dict) else None
                result['truncations'].append({'evidence': evidence,
                    'completion_tokens': count if type(count) is int and count >= 0 else None,
                    'tools_executed': False if (key := (event.get('run_id'), event.get('phase'), event.get('event_id')))
                        in not_executed and response_ids[key] == 1 else None})
            elif event.get('type') == 'output_recovery':
                if event.get('status') not in ('scheduled', 'response_complete', 'stopped'):
                    raise QualityError('INVALID_TRACE', '无法识别恢复状态，请查看原始记录。', 422)
                result['recovery'].append({k: event.get(k) for k in (
                    'status', 'reason', 'attempt', 'mode', 'normal_cap', 'recovery_cap', 'request_cap')} | {'evidence': evidence})
            elif event.get('type') == 'final_response':
                result['stop'] = {'reason': event.get('stop_reason'), 'text': event.get('text'), 'evidence': evidence}
    # Old runner may halt before a model_response event. Only explicit response
    # bodies qualify; generic protocol_error text never proves length.
    logs = [p for p in paths if PurePosixPath(p).name == 'model-requests.jsonl']
    shared = not bool(logs)
    if shared:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
        logs = [f['path'] for f in manifest['files'] if PurePosixPath(f['path']).name == 'requests.jsonl']
    seen = set()
    for path in logs:
        for line, row in _rows(folder, path):
            if (shared or 'case' in row) and row.get('case') != case['id']:
                continue
            if row.get('kind') != 'response' or not _is_length(raw := row.get('body')):
                continue
            fingerprint = _fingerprint(raw)
            key = (row.get('number') if type(row.get('number')) is int else None, fingerprint)
            if fingerprint in event_bodies or key in seen:
                continue
            seen.add(key)
            count = (raw.get('usage') or {}).get('completion_tokens') if isinstance(raw.get('usage'), dict) else None
            result['truncations'].append({'evidence': _reference(path, line, row, request=True),
                'completion_tokens': count if type(count) is int and count >= 0 else None, 'tools_executed': None})
    return result
