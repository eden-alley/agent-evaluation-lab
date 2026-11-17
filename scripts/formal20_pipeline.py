"""Resumable archive/statistics/review delivery; no task execution or model calls."""
import json
from pathlib import Path
from urllib.parse import quote

from capability_review import Analysis, ReviewClientError, prepare_review_files, save, submit_review_files
from formal20_archive import digest, export_run, publish_archive, read, verify_archive


def _result(control, state):
    review = active_review_dir(control, state)
    return {**state, 'control_dir': str(control), 'active_review_dir': str(review),
            'packet': str(review / 'packet.json'), 'analysis': str(review / 'analysis.json'),
            'model_calls': 0, 'evaluation_runs': 0,
            'next_action': '发起评测的同一外部Agent继续本次任务：读取Skill正文.md与materials.json，分析关键题，调用提交程序并取得报告回执；analysis_pending尚未完成全部交付。'
                           if state['status'] == 'analysis_pending' else None}


def active_review_dir(control, state):
    control = Path(control).resolve()
    review = Path(state.get('active_review_dir') or control).resolve()
    if not review.is_relative_to(control):
        raise ValueError('The active review must remain inside the original delivery control directory')
    return review


def _state(control, state, status, **fields):
    state.update(status=status, last_successful_stage=status, **fields)
    state.pop('error', None)
    save(control / 'delivery-state.json', state)


def _binding(config, run_dir):
    # JSON normalization preserves Path values across a process restart.
    return json.loads(json.dumps({'config': config, 'run_dir': str(Path(run_dir).resolve())}, default=str))


def _validate_destination(config, api_client):
    if api_client is None or not callable(getattr(api_client, 'request', None)):
        raise ValueError('An explicit platform API client is required; no default platform fallback is allowed')
    if not config.get('data_root') or not config.get('archive_root'):
        raise ValueError('Explicit data_root and archive_root directories are required')
    app = getattr(getattr(api_client, 'client', api_client), 'app', None)
    db_path = getattr(getattr(app, 'state', None), 'db_path', None)
    if db_path and Path(db_path).resolve().parent != Path(config['data_root']).resolve():
        raise ValueError('data_root differs from the explicitly injected platform app')
    health = api_client.request('GET', '/health')
    storage = health.get('storage', {})
    if not storage.get('data_root') or not storage.get('evaluation_runs_root'):
        raise ValueError('Platform storage identity is missing; update the platform before execution')
    expected = Path(config['data_root']).resolve()
    if (Path(storage['data_root']).resolve() != expected or
            Path(storage['evaluation_runs_root']).resolve() != expected / 'evaluation-runs'):
        raise ValueError('data_root differs from the HTTP platform storage identity')
    if config.get('validation'):
        # The caller supplies an isolated TestClient or explicit validation URL client.
        # Never construct capability_review.Client() here (its legacy default is daily 8100).
        http = getattr(api_client, 'http', None)
        base = str(getattr(http, 'base_url', '')) if http is not None else ''
        if base and ':8100' in base:
            raise ValueError('Validation cannot use the daily platform port 8100')
    return health


def validate_delivery_paths(config, run_dir=None):
    """Check the same effective paths before dispatch and before publication."""
    run = Path(run_dir or config['out']).resolve() if run_dir or config.get('out') else None
    control_value = config.get('control_dir') or (run.with_name(run.name + '-delivery') if run else None)
    control = Path(control_value).resolve() if control_value else None
    archive = Path(config['archive_root']).resolve()
    published = Path(config['data_root']).resolve() / 'evaluation-runs'
    reservations = Path(config['data_root']).resolve() / 'execution-approvals'
    paths = [path for path in (run, control, archive, published, reservations) if path is not None]
    for index, first in enumerate(paths):
        for second in paths[index + 1:]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError('Delivery control and execution must remain outside immutable archives and each other')
    return control


def finalize_run(config, run_dir, api_client):
    """Archive/import once, create one comparison, then provide a fixed analysis packet."""
    _validate_destination(config, api_client)
    run_dir = Path(run_dir).resolve()
    control = validate_delivery_paths(config, run_dir)
    archive_root = Path(config['archive_root']).resolve()
    data_root = Path(config['data_root']).resolve()
    control.mkdir(parents=True, exist_ok=True)
    context = _binding(config, run_dir)
    context_path = control / 'delivery-context.json'
    if context_path.exists() and read(context_path) != context:
        raise ValueError('Delivery binding changed; resume requires the original configuration')
    if not context_path.exists():
        save(context_path, context)
    state = read(control / 'delivery-state.json', {'status': 'execution_complete', 'last_successful_stage': 'execution_complete'})
    try:
        stage = export_run(config, run_dir, archive_root / config['run_id'])
        archive = publish_archive(stage, data_root / 'evaluation-runs')
        identity = verify_archive(archive)
        if state['status'] not in ('analysis_pending', 'delivery_complete', 'report_received'):
            _state(control, state, 'archive_imported', archive=str(archive), **identity)
        if not (control / 'import-receipt.json').exists():
            save(control / 'import-receipt.json', {'archive': str(archive), **identity})
        if not config.get('baseline_run_id'):
            _state(control, state, 'baseline_required', archive=str(archive), **identity)
            return _result(control, state)
        if not config.get('workflow'):
            raise ValueError('A fixed workflow skill_id/version_id/content_hash is required')
        request_path = control / 'comparison-request.json'
        if request_path.exists():
            request = read(request_path)
        else:
            body = {'name': config.get('comparison_name', config['name']),
                    'objective': config.get('objective', 'Compare saved checks and evidence; offline validation, not a model capability result.' if config.get('validation') else 'Compare saved checks and original task evidence.'),
                    'baseline_run_id': config['baseline_run_id'], 'candidate': {'kind': 'run', 'run_id': config['run_id']},
                    'case_ids': config['case_ids'], 'workflow': config['workflow'],
                    'analyst': config.get('analyst', {'kind': 'offline_fixture' if config.get('validation') else 'external_agent',
                               'name': 'offline integration validation' if config.get('validation') else 'external run initiator'})}
            request = {'request_id': 'delivery-' + digest(body)[:48], **body}
            save(request_path, request)
        comparison_path = control / 'comparison.json'
        if comparison_path.exists():
            comparison = read(comparison_path)
        else:
            comparison = api_client.request('POST', '/comparisons', json=request)
            save(comparison_path, comparison)
        comparison_id = comparison['id']
        if not comparison.get('metric_report') or not comparison.get('metrics_snapshot'):
            raise ValueError('Platform comparison did not persist the required machine statistics snapshot')
        save(control / 'metric-report.json', comparison['metric_report'])
        save(control / 'metrics-snapshot.json', comparison['metrics_snapshot'])
        if state['status'] not in ('analysis_pending', 'delivery_complete', 'report_received'):
            _state(control, state, 'statistics_ready', comparison_id=comparison_id)
        packet = prepare_review_files(api_client, comparison_id, control,
                    review_scope=config.get('review_scope', 'focused'), explain_case_ids=config.get('explain_case_ids'))
        if packet['workflow'] != config['workflow']:
            raise ValueError('Prepared packet differs from the frozen workflow')
        if state['status'] not in ('delivery_complete', 'report_received'):
            _state(control, state, 'analysis_pending', comparison_id=comparison_id,
                   delivery_id=packet['delivery_id'], packet_hash=packet['packet_hash'])
        return _result(control, state)
    except Exception as exc:
        state['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        save(control / 'delivery-state.json', state)
        raise


def resume_delivery(control_dir, api_client):
    """Continue only delivery stages; never rerun the task, grader or prepare packet."""
    control = Path(control_dir).resolve()
    context = read(control / 'delivery-context.json')
    if not context:
        raise ValueError('Missing original delivery context')
    state = read(control / 'delivery-state.json', {})
    review = active_review_dir(control, state)
    if (review / 'rejection.json').exists():
        # Continue exposes the correction handoff; it does not resend a known
        # rejected analysis or silently create a new submission.
        return _result(control, state)
    if (review / 'request.json').exists():
        return submit_analysis_task(control, review / 'analysis.json', api_client)
    if review != control:
        return submit_analysis_task(control, review / 'analysis.json', api_client)
    return finalize_run(context['config'], context['run_dir'], api_client)


def _replacement_review(control, review, state, content):
    rejected = read(review / 'rejection.json')
    request = read(review / 'request.json')
    if not rejected or not request or rejected['request_id'] != request['request_id']:
        raise ValueError('A matching confirmed rejection is required before correcting a saved request')
    error = rejected.get('response_body', {})
    error = error.get('error', error) if isinstance(error, dict) else {}
    stale = isinstance(error, dict) and error.get('code') in ('STALE_REVIEW', 'STALE_REVIEW_PACKET')
    if not stale and Analysis.model_validate(content).model_dump() == request['analysis']:
        raise ReviewClientError('原请求已被明确拒绝；请修正分析后通过原任务再次 submit。',
                                status_code=rejected['status_code'], response_body=rejected['response_body'])
    attempts = control / 'review-attempts'
    attempts.mkdir(exist_ok=True)
    index = 1
    while (attempts / f'{index:04d}').exists():
        index += 1
    replacement = attempts / f'{index:04d}'
    replacement.mkdir()
    packet = read(review / 'packet.json')
    # Persist the link before a prepare attempt, so a lost prepare response keeps
    # its original directory and cannot cause another delivery on resume.
    save(replacement / 'analysis.json', content)
    save(replacement / 'replacement.json', {'previous_review_dir': str(review),
         'rejected_request_id': request['request_id'], 'comparison_id': packet['comparison_id']})
    if not stale:
        save(replacement / 'packet.json', packet)
    state['active_review_dir'] = str(replacement)
    save(control / 'delivery-state.json', state)
    return replacement


def submit_analysis_task(control_dir, analysis_path, api_client):
    """Submit an external analysis and mark complete only after report plus receipt exist."""
    control = Path(control_dir).resolve()
    context = read(control / 'delivery-context.json')
    if not context or not (control / 'packet.json').is_file():
        raise ValueError('A fixed original packet and delivery context are required')
    config = context['config']
    _validate_destination(config, api_client)
    state = read(control / 'delivery-state.json', {})
    review = active_review_dir(control, state)
    origin = config.get('analysis_origin', 'offline_program' if config.get('validation') else 'external_agent')
    try:
        analysis_path = Path(analysis_path).resolve()
        content = read(analysis_path)
        Analysis.model_validate(content)
        if (review / 'rejection.json').exists():
            review = _replacement_review(control, review, state, content)
        if review != control:
            packet = prepare_review_files(api_client, state['comparison_id'], review,
                review_scope=config.get('review_scope', 'focused'), explain_case_ids=config.get('explain_case_ids'))
            if packet['workflow'] != config['workflow']:
                raise ValueError('Prepared replacement differs from the frozen workflow')
            state.update(delivery_id=packet['delivery_id'], packet_hash=packet['packet_hash'])
            save(control / 'delivery-state.json', state)
        fixed_analysis = review / 'analysis.json'
        if analysis_path != fixed_analysis:
            if (review / 'request.json').exists() and read(fixed_analysis) != content:
                raise ValueError('Analysis is already bound to the original saved request')
            if not (review / 'request.json').exists():
                save(fixed_analysis, content)
            analysis_path = fixed_analysis
        report, receipt = submit_review_files(api_client, review / 'packet.json', analysis_path,
                                      origin=origin, frontend_url=config.get('frontend_url'))
        _state(control, state, 'report_received', report_id=report['id'], receipt=receipt)
        # Receipt creation is separate from the immutable archive and must precede completion.
        _state(control, state, 'delivery_complete', report_id=report['id'], receipt=receipt,
               quality_status='structure_and_references_checked; semantic_quality_not_calibrated')
        return _result(control, state)
    except Exception as exc:
        state['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        save(control / 'delivery-state.json', state)
        raise
