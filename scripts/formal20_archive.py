"""Export saved execution evidence to the existing platform archive contract.

This module reads results and grades; it never imports a runner or calls a scorer.
"""
from collections import Counter
from decimal import Decimal
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('Invalid archive or case identifier')
    return value


def record(path, root):
    raw = path.read_bytes()
    return {'path': path.relative_to(root).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def verify_archive(folder):
    folder = Path(folder).resolve()
    manifest = read(folder / 'manifest.json')
    run = read(folder / 'run.json')
    if not manifest or not run:
        raise ValueError('Archive requires run.json and manifest.json')
    identifier(run['id'])
    seen = set()
    for item in manifest['files']:
        relative = PurePosixPath(item['path'])
        if ('\\' in item['path'] or ':' in item['path'] or relative.is_absolute()
                or '..' in relative.parts or item['path'] in seen or item['path'] == 'manifest.json'):
            raise ValueError('Invalid or duplicate manifest path')
        seen.add(item['path'])
        target = folder / item['path']
        if target.is_symlink() or not target.resolve().is_relative_to(folder) or not target.is_file():
            raise ValueError('Archive evidence is missing or escapes its directory')
        if record(target, folder) != item:
            raise ValueError('Archive evidence hash changed: ' + item['path'])
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != seen | {'manifest.json'} or 'run.json' not in seen:
        raise ValueError('Manifest must cover every archive file')
    for case in run.get('cases', []):
        for item in case.get('files', []):
            if item not in manifest['files']:
                raise ValueError('Case references an unmanifested file')
    return {'run_id': run['id'], 'manifest_hash': hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest(),
            'run_hash': hashlib.sha256((folder / 'run.json').read_bytes()).hexdigest()}


def _suite(config):
    value = config['suite']
    if isinstance(value, (str, Path)):
        path = Path(value)
        value = read(path / 'cases.json' if path.is_dir() else path)
        if isinstance(value, dict) and isinstance(value.get('cases'), str):
            value = read(path.parent / value['cases'])
    if isinstance(value, dict):
        value = value.get('cases', value)
        if isinstance(value, dict):
            value = list(value.values())
    if not isinstance(value, list):
        raise ValueError('suite must provide frozen case metadata')
    return {case['id']: case for case in value}


def _task(config, case, checks):
    fixed = config.get('task_metadata', {}).get(case['id'], case.get('task'))
    if fixed:
        task = copy.deepcopy(fixed)
        if not task.get('turns') or not task.get('controls') or not task.get('checks'):
            raise ValueError('Explicit task metadata must include turns, controls and checks')
        original = [t.get('content') if isinstance(t, dict) else t for t in case.get('turns', [])]
        supplied = [t.get('content') if isinstance(t, dict) else t for t in task['turns']]
        if original and supplied != original:
            raise ValueError('Task metadata differs from frozen task turns')
        if 'allowed' in case and task['controls'].get('allowed_changes') != case['allowed']:
            raise ValueError('Task metadata differs from frozen allowed changes')
        return task
    if not case.get('turns'):
        raise ValueError('Frozen task turns are required')
    criteria = case.get('checks') or [{'id': c['id'], 'rule': c['rule']} for c in checks]
    return {'turns': [t if isinstance(t, dict) else {'index': i, 'role': 'user', 'content': t}
                      for i, t in enumerate(case['turns'], 1)],
            'source': case.get('source'), 'controls': {'allowed_changes': case.get('allowed', []),
            'requests_per_case_cap': config.get('max_requests_per_case', config.get('per_case_limit')),
            'attempts': config.get('attempts_per_case', 1), 'controller': case.get('module')},
            'checks': criteria, 'difficulty_basis': case.get('difficulty_basis', case.get('difficulty_design', case.get('difficulty')))}


def _checks(grade, case):
    raw = grade.get('checks', {})
    criteria = {c['id']: c for c in case.get('checks', [])}
    values = raw.items() if isinstance(raw, dict) else ((c['id'], c) for c in raw)
    return [{'id': key, **copy.deepcopy(value),
             'rule': value.get('rule', criteria.get(key, {}).get('rule', '原题冻结检查 ' + key)),
             'required_for_task': value.get('required_for_task', True)} for key, value in values]


def _case_usage(run_dir, budget):
    """Project the final durable record set, never sum repeated journal snapshots."""
    path = run_dir / 'request-ledger.jsonl'
    if not path.is_file():
        return {}
    last = None
    try:
        with path.open('r', encoding='utf-8-sig') as stream:
            for line in stream:
                if not line.endswith('\n'):
                    return {}  # A partial journal is evidence, not reliable usage.
                if line.strip():
                    last = json.loads(line)
        if (not last or not isinstance(last.get('records'), list)
                or (budget.get('journal_sequence') is not None and last.get('sequence') != budget['journal_sequence'])):
            return {}
        records = last['records']
        if len({r['request_id'] for r in records}) != len(records):
            return {}
    except (OSError, ValueError, TypeError, KeyError):
        return {}
    grouped = {}
    for item in records:
        cid = item.get('case_id')
        row = grouped.setdefault(cid, {'requests': 0, 'known': 0, 'prompt': 0, 'completion': 0, 'cost': Decimal(0), 'cost_known': 0})
        row['requests'] += 1
        usage = item.get('response_usage')
        if item.get('status') == 'settled' and isinstance(usage, dict) and all(
                type(usage.get(key)) is int and usage[key] >= 0 for key in ('prompt_tokens', 'completion_tokens')):
            row['known'] += 1
            row['prompt'] += usage['prompt_tokens']
            row['completion'] += usage['completion_tokens']
            cost = (item.get('settlement_result') or {}).get('cost')
            if cost is not None:
                row['cost'] += Decimal(str(cost))
                row['cost_known'] += 1
    projected = {}
    for cid, row in grouped.items():
        requests = budget.get('per_case', {}).get(cid)
        complete = row['known'] == row['requests'] and requests == row['requests']
        cost = str(row['cost']) if complete and row['cost_known'] == row['requests'] else None
        projected[cid] = {'prompt_tokens': row['prompt'] if complete else None,
            'completion_tokens': row['completion'] if complete else None,
            'known_prompt_tokens': row['prompt'], 'known_completion_tokens': row['completion'],
            'unknown_requests': max(row['requests'] - row['known'], (requests or 0) - row['known']) if isinstance(requests, int) else row['requests'] - row['known'],
            'known_estimated_cost': str(row['cost']), 'estimated_cost': cost, 'currency': budget.get('currency'),
            'estimated_cny': cost if budget.get('currency') == 'CNY' else None,
            'estimated_usd': cost if budget.get('currency') == 'USD' else None,
            'usage_source': 'final durable request-ledger records; each physical request_id counted once'}
    return projected


def export_run(config, run_dir, destination):
    """Copy original evidence and project metadata; return an immutable stage Path."""
    run_dir, destination = Path(run_dir).resolve(), Path(destination).resolve()
    run_id = identifier(config['run_id'])
    if destination.is_relative_to(run_dir):
        raise ValueError('Archive staging must be outside execution evidence')
    if destination.exists():
        identity = verify_archive(destination)
        if identity['run_id'] != run_id or read(destination / 'run.json').get('export_config_hash') != digest(config):
            raise ValueError('Archive stage already belongs to different inputs')
        return destination
    suite = _suite(config)
    case_ids = config['case_ids']
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError('case_ids must be nonempty and unique')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # A full run id plus UUID needlessly pushes valid Windows destinations past MAX_PATH.
    # Keep staging unique and on the same filesystem for the atomic rename.
    temp = Path(tempfile.mkdtemp(prefix='.archive-', dir=destination.parent))
    try:
        budget = read(run_dir / 'budget.json', {})
        case_usage = _case_usage(run_dir, budget)
        for name in ('budget.json', 'requests.jsonl', 'request-ledger.jsonl', 'execution-state.json', 'summary.json'):
            if (run_dir / name).is_file():
                shutil.copyfile(run_dir / name, temp / name)
        cases = []
        for cid in case_ids:
            identifier(cid)
            if cid not in suite:
                raise ValueError('Missing frozen case metadata: ' + cid)
            case = suite[cid]
            source = run_dir / cid
            if source.is_dir():
                for path in source.rglob('*'):
                    if path.is_symlink() or not path.resolve().is_relative_to(run_dir):
                        raise ValueError('Execution evidence cannot contain links outside its directory')
                    if path.is_file():
                        target = temp / path.relative_to(run_dir)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, target)
            result = read(source / 'result.json', {})
            grade = read(source / 'grade/grade.json', {})
            checks = _checks(grade, case)
            state = read(source / 'worker-state.json', {})
            error = result.get('error') or result.get('infrastructure_error')
            if state.get('status') not in (None, 'completed'):
                error = error or state.get('reason') or state['status']
            runtime_error = read(source / 'runtime-error.json', {})
            if state.get('status') != 'completed':
                error = error or runtime_error.get('type')
            phases = result.get('phases', [])
            complete = bool(result) and bool(grade) and not error and all(p.get('stop_reason') not in ('api_error', 'interrupted', 'model_error', 'usage_unknown') for p in phases)
            invalid = any(c.get('invalid') for c in checks)
            verdict = grade.get('verdict', 'unknown') if complete else 'unknown'
            per_case = budget.get('per_case', {}).get(cid)
            metrics = copy.deepcopy(result.get('metrics', {}))
            metrics.update(model_requests=per_case if isinstance(per_case, (int, float)) else result.get('requests'),
                           elapsed_seconds=result.get('seconds', metrics.get('elapsed_seconds')))
            if isinstance(per_case, dict):
                metrics.update(per_case)
            metrics.update(case_usage.get(cid, {}))
            files = [record(p, temp) for p in sorted((temp / cid).rglob('*')) if p.is_file()]
            cases.append({'id': cid, 'title': case.get('title', cid), 'group': case.get('group'),
                'difficulty_design': case.get('difficulty_design', case.get('difficulty')),
                'task': _task(config, case, checks), 'checks': checks, 'automatic_verdict': grade.get('verdict', 'unknown'),
                'core_acceptance': 'unknown' if invalid else verdict, 'valid_for_scoring': complete and not invalid and verdict in ('pass', 'fail'),
                'run_complete': complete, 'execution_status': ('completed' if complete else state.get('status', 'incomplete' if result else 'not_run')),
                'exclusion_reason': error or ('invalid original check' if invalid else 'missing execution result or original grade' if not complete else None),
                'infrastructure_error': error, 'final_response': phases[-1].get('text') if phases else None,
                'metrics': metrics, 'files': files})
        counts = Counter(c['core_acceptance'] for c in cases)
        valid = sum(c['valid_for_scoring'] for c in cases)
        unresolved = budget.get('unresolved_requests', budget.get('unknown_requests', []))
        unknown_records = unresolved.values() if isinstance(unresolved, dict) else unresolved
        unknown_reserve = str(sum((Decimal(str(item.get('reserve', '0'))) for item in unknown_records), Decimal(0))) if isinstance(unresolved, (list, dict)) else '0'
        unknown_cost = budget.get('reserved_unknown_cny', budget.get('reserved_unknown', unknown_reserve))
        currency = budget.get('currency', config.get('currency', 'CNY' if 'reserved_unknown_cny' in budget else None))
        known_cost = budget.get('known_estimated_cny', budget.get('estimated_cost_at_peak'))
        full_cost = None if unresolved or budget.get('inflight_count') or str(unknown_cost) not in ('0', '0.0', '0.00', 'None') else known_cost
        run = {'id': run_id, 'project_id': config['project_id'], 'project_name': config['project_name'],
               'name': config['name'], 'model': config['model'], 'harness_version': config['version'],
               'source_harness': config['source_harness'], 'dataset': config.get('dataset', {'version': config.get('suite_version'), 'name': config.get('suite_name')}),
               'validation': bool(config.get('validation')), 'purpose': 'offline_validation' if config.get('validation') else 'evaluation',
               'is_simulation': bool(config.get('validation')), 'export_config_hash': digest(config),
               'case_count': len(cases), 'executed_case_count': sum(c['execution_status'] != 'not_run' for c in cases),
               'valid_case_count': valid, 'valid_pass_rate': counts['pass'] / valid if valid else None,
               'invalid_case_count': sum(any(ch.get('invalid') for ch in c['checks']) for c in cases),
               'not_run_case_count': sum(c['execution_status'] == 'not_run' for c in cases),
               'counts': dict(counts), 'execution_status_counts': dict(Counter(c['execution_status'] for c in cases)),
               'requests': budget.get('requests'), 'prompt_tokens': budget.get('prompt_tokens'),
               'completion_tokens': budget.get('completion_tokens'), 'responses': budget.get('response_count', budget.get('responses')),
               'unknown_requests': len(unresolved) if isinstance(unresolved, (list, dict)) else budget.get('unknown_count'),
               'currency': currency, 'reserved_unknown': unknown_cost, 'known_estimated_cost': known_cost, 'estimated_cost': full_cost,
               'reserved_unsettled': budget.get('reserved_total'), 'inflight_requests_count': budget.get('inflight_count'),
               'reserved_unknown_cny': unknown_cost if currency == 'CNY' else None,
               'known_estimated_cny': known_cost if currency == 'CNY' else None,
               'estimated_cny': full_cost if currency == 'CNY' else None,
               'cases': cases}
        if config.get('validation') and 'validation' not in run['name'].lower() and '验证' not in run['name']:
            run['name'] = '[offline validation] ' + run['name']
        write(temp / 'run.json', run)
        write(temp / 'manifest.json', {'schema_version': 1, 'run_id': run_id,
              'files': [record(p, temp) for p in sorted(temp.rglob('*')) if p.is_file()]})
        verify_archive(temp)
        temp.rename(destination)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return destination


def publish_archive(stage, targetRoot):
    """Hash-verify then atomically publish; same bytes are idempotent, drift refuses."""
    stage, target_root = Path(stage).resolve(), Path(targetRoot).resolve()
    identity = verify_archive(stage)
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / identity['run_id']
    if target.exists():
        if verify_archive(target) != identity:
            raise ValueError('Refusing to replace an archive with different contents')
        return target
    # Keep incomplete run.json files outside the platform's */run.json scan.
    # Sibling directories share a filesystem, so the final rename stays atomic.
    temp = target_root.parent / ('.' + target_root.name + '-publish-' + uuid.uuid4().hex)
    try:
        shutil.copytree(stage, temp)
        if verify_archive(temp) != identity:
            raise ValueError('Archive copy differs from stage')
        try:
            temp.rename(target)
        except FileExistsError:
            if verify_archive(target) != identity:
                raise ValueError('Concurrent publication has different contents')
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return target
