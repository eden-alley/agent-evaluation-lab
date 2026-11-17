"""Offline archive/delivery integration against the real isolated FastAPI app."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
from fastapi.testclient import TestClient
from formal20_archive import export_run, publish_archive, verify_archive
from formal20_pipeline import finalize_run, resume_delivery, submit_analysis_task
from capability_review import ReviewClientError


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


class Api:
    def __init__(self, client):
        self.client = client
        self.calls = []
        self.lose_response = None

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        response = self.client.request(method, '/api/v1' + path, **kwargs)
        if response.status_code >= 400:
            raise ReviewClientError(response.text, status_code=response.status_code,
                                    response_body=response.json())
        if self.lose_response == path:
            self.lose_response = None
            raise ReviewClientError('response lost after durable server commit')
        return response.json()


class DeliveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows path-length regression')
    def test_archive_temporary_name_does_not_extend_long_final_path(self):
        checkpoint=self.run/'U05/checkpoint/archive'/('a'*32+'.json')
        save(checkpoint,{'saved':'evidence'})
        padding='x'*(180-len(str(self.root))-1)
        destination=self.root/padding
        self.assertLess(len(str(destination/'U05/checkpoint/archive'/checkpoint.name)),260)
        stage=export_run(self.config,self.run,destination)
        self.assertEqual((stage/'U05/checkpoint/archive'/checkpoint.name).read_bytes(),checkpoint.read_bytes())
        self.assertEqual(verify_archive(stage)['run_id'],self.config['run_id'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='real-delivery-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # lab.main also constructs its module-level app; bind that import to this
        # test's temporary data directory rather than the checkout's default DB.
        with patch.dict(os.environ, {'LAB_DB_PATH': str(self.root / 'platform/lab.sqlite3')}):
            from lab.main import create_app
        self.client = TestClient(create_app(self.root / 'platform/lab.sqlite3'))
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))
        self.api = Api(self.client)
        project = self.api.request('POST', '/projects', json={'name': 'offline validation'})
        skill = self.api.request('POST', '/skills', json={'name': 'fixed validation method', 'kind': 'evaluation', 'description': 'offline'})
        version = self.api.request('POST', f"/skills/{skill['id']}/versions", json={'content': '---\nversion: 0.9.0\n---\nRead evidence.', 'change_note': 'offline'})
        self.api.request('POST', f"/skills/{skill['id']}/versions/{version['id']}/publish")
        self.config = {'run_id': 'candidate-validation', 'project_id': project['id'], 'project_name': 'offline validation',
                       'name': 'fake-model integration validation', 'model': 'scripted_api', 'validation': True,
                       'version': 'test', 'source_harness': {'sha256': 'f' * 64},
                       'suite': [{'id': 'U05', 'title': 'validation task', 'turns': ['Preserve tests and write report.'],
                                  'allowed': ['report.md'], 'source': 'frozen fixture', 'module': 'fixture',
                                  'checks': [{'id': 'report', 'rule': 'report exists'}]}],
                       'case_ids': ['U05'], 'archive_root': str(self.root / 'archives'),
                       'data_root': str(self.root / 'platform'), 'baseline_run_id': 'baseline-validation',
                       'workflow': {k: version[k] if k != 'skill_id' else skill['id'] for k in ('skill_id', 'version_id', 'content_hash') if k != 'version_id'}}
        self.config['workflow']['version_id'] = version['id']
        self.run = self.make_run('candidate')
        baseline = {**self.config, 'run_id': 'baseline-validation'}
        stage = export_run(baseline, self.make_run('baseline'), self.root / 'baseline-stage')
        publish_archive(stage, self.root / 'platform/evaluation-runs')

    def make_run(self, name):
        run = self.root / name
        save(run / 'U05/result.json', {'id': 'U05', 'phases': [{'index': 1, 'text': 'done', 'stop_reason': 'end_turn'}], 'requests': 2, 'seconds': 1.2})
        save(run / 'U05/grade/grade.json', {'id': 'U05', 'verdict': 'pass', 'checks': {'report': {'value': 1, 'evidence': 'workspace/report.md'}}})
        (run / 'U05/workspace').mkdir()
        (run / 'U05/workspace/report.md').write_text('offline validation artifact', encoding='utf-8')
        (run / 'U05/events.jsonl').write_text(json.dumps({'type': 'tool_call', 'event_id': 1, 'tool': 'read_file'}) + '\n', encoding='utf-8')
        save(run / 'budget.json', {'requests': 2, 'per_case': {'U05': 2}, 'prompt_tokens': 15, 'completion_tokens': 3, 'reserved_unknown_cny': '0.1', 'unresolved_requests': [{'case': 'U05'}]})
        return run

    def test_export_preserves_original_grade_task_and_unknowns(self):
        stage = export_run(self.config, self.run, self.root / 'stage')
        bundle = json.loads((stage / 'run.json').read_text(encoding='utf-8'))
        case = bundle['cases'][0]
        self.assertEqual((stage / 'U05/grade/grade.json').read_bytes(), (self.run / 'U05/grade/grade.json').read_bytes())
        self.assertEqual(case['checks'][0]['value'], 1)
        self.assertEqual(case['task']['controls']['allowed_changes'], ['report.md'])
        self.assertEqual(case['task']['turns'][0]['content'], self.config['suite'][0]['turns'][0])
        self.assertIsNone(bundle['estimated_cny'])
        self.assertTrue(bundle['validation'])
        self.assertIn('validation', bundle['name'])
        verify_archive(stage)
        target = publish_archive(stage, self.root / 'published')
        self.assertEqual(publish_archive(stage, self.root / 'published'), target)
        (target / 'U05/workspace/report.md').write_text('drift', encoding='utf-8')
        with self.assertRaises(ValueError):
            publish_archive(stage, self.root / 'published')

    def test_publish_never_exposes_partial_bundle_to_platform_run_list(self):
        import formal20_archive as archive
        stage = export_run(self.config, self.run, self.root / 'atomic-stage')
        original = archive.shutil.copytree
        def inspect_before_rename(*args, **kwargs):
            result = original(*args, **kwargs)
            visible = self.api.request('GET', '/evaluation-runs')['items']
            self.assertEqual([item['id'] for item in visible], ['baseline-validation'])
            return result
        with patch.object(archive.shutil, 'copytree', inspect_before_rename):
            publish_archive(stage, self.root / 'platform/evaluation-runs')
        self.assertEqual(len(self.api.request('GET', '/evaluation-runs')['items']), 2)

    def test_imported_run_gets_comparison_and_statistics_without_analysis(self):
        result = finalize_run(self.config, self.run, self.api)
        self.assertEqual(result['status'], 'analysis_pending')
        comparison = self.api.request('GET', '/comparisons/' + result['comparison_id'])
        self.assertIsNone(comparison['latest_report'])
        self.assertTrue(comparison['metric_report']['quality'])
        self.assertEqual(comparison['queue'][0]['task_state'], 'same')
        for name in ('packet.json', 'materials.json', 'Skill正文.md', '指标升降表.md', '材料摘要.md', 'cases/U05.json'):
            self.assertTrue((Path(result['control_dir']) / name).is_file(), name)

    def test_finalize_is_idempotent_and_recovers_lost_create_response(self):
        self.api.lose_response = '/comparisons'
        with self.assertRaises(ReviewClientError):
            finalize_run(self.config, self.run, self.api)
        control = self.run.with_name(self.run.name + '-delivery')
        request = (control / 'comparison-request.json').read_bytes()
        result = resume_delivery(control, self.api)
        packet = (control / 'packet.json').read_bytes()
        again = finalize_run(self.config, self.run, self.api)
        self.assertEqual(result['comparison_id'], again['comparison_id'])
        self.assertEqual((control / 'comparison-request.json').read_bytes(), request)
        self.assertEqual((control / 'packet.json').read_bytes(), packet)
        self.assertEqual(len(self.api.request('GET', '/comparisons')['items']), 1)

    def test_finalize_is_idempotent_at_each_saved_stage_boundary(self):
        import formal20_pipeline as pipeline
        original = pipeline._state
        for stage in ('archive_imported', 'statistics_ready', 'analysis_pending'):
            with self.subTest(stage=stage):
                config = {**self.config, 'run_id': 'validation-' + stage}
                run = self.make_run(stage)
                interrupted = False
                def stop_after_save(control, state, status, **fields):
                    nonlocal interrupted
                    original(control, state, status, **fields)
                    if status == stage and not interrupted:
                        interrupted = True
                        raise RuntimeError('offline crash injection after ' + status)
                with patch.object(pipeline, '_state', stop_after_save):
                    with self.assertRaisesRegex(RuntimeError, 'offline crash'):
                        finalize_run(config, run, self.api)
                result = finalize_run(config, run, self.api)
                self.assertEqual(result['status'], 'analysis_pending')
                fixed = (Path(result['control_dir']) / 'packet.json').read_bytes()
                self.assertEqual(resume_delivery(result['control_dir'], self.api)['comparison_id'], result['comparison_id'])
                self.assertEqual((Path(result['control_dir']) / 'packet.json').read_bytes(), fixed)
        self.assertEqual(len(self.api.request('GET', '/comparisons')['items']), 3)

    def test_missing_baseline_archives_without_fake_comparison(self):
        config = {**self.config, 'baseline_run_id': None}
        result = finalize_run(config, self.run, self.api)
        self.assertEqual(result['status'], 'baseline_required')
        self.assertTrue(Path(result['archive']).is_dir())
        self.assertEqual(self.api.request('GET', '/comparisons')['items'], [])

    def test_validation_refuses_implicit_daily_platform(self):
        config = {k: v for k, v in self.config.items() if k != 'data_root'}
        with self.assertRaises(ValueError):
            finalize_run(config, self.run, self.api)
        with self.assertRaises(ValueError):
            finalize_run(self.config, self.run, None)

    def test_preparation_timeout_never_issues_another_delivery(self):
        # Create succeeds, prepare commits, its response is lost.
        original = self.api.request
        def request(method, path, **kwargs):
            if method == 'POST' and path.endswith('/review-materials'):
                self.api.lose_response = path
            return original(method, path, **kwargs)
        self.api.request = request
        with self.assertRaises(ReviewClientError):
            finalize_run(self.config, self.run, self.api)
        count = len([c for c in self.api.calls if c[1].endswith('/review-materials')])
        self.api.request = original
        control = self.run.with_name(self.run.name + '-delivery')
        with self.assertRaisesRegex(ReviewClientError, '不会自动再次 prepare'):
            resume_delivery(control, self.api)
        self.assertEqual(len([c for c in self.api.calls if c[1].endswith('/review-materials')]), count)
        self.assertFalse((control / 'packet.json').exists())

    def test_missing_and_invalid_grades_remain_unknown(self):
        grade = self.run / 'U05/grade/grade.json'
        save(grade, {'id': 'U05', 'verdict': 'unknown', 'checks': {'report': {'value': 'unknown', 'invalid': True}}})
        stage = export_run(self.config, self.run, self.root / 'invalid-stage')
        case = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]
        self.assertEqual(case['core_acceptance'], 'unknown')
        self.assertTrue(case['checks'][0]['invalid'])
        self.assertFalse(case['valid_for_scoring'])

    def test_current_coordinator_unknown_reservations_are_not_reported_as_free(self):
        save(self.run / 'budget.json', {'currency': 'CNY', 'requests': 2, 'per_case': {'U05': 2},
             'prompt_tokens': 15, 'completion_tokens': 3, 'reserved_total': '0.35', 'inflight_count': 1,
             'estimated_cost_at_peak': '0.12', 'unknown_count': 1, 'response_count': 1,
             'unknown_requests': {'request-2': {'case_id': 'U05', 'reserve': '0.25'}}})
        stage = export_run(self.config, self.run, self.root / 'unknown-stage')
        run = json.loads((stage / 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(run['unknown_requests'], 1)
        self.assertEqual(run['reserved_unknown_cny'], '0.25')
        self.assertIsNone(run['estimated_cny'])
        self.assertEqual(run['known_estimated_cny'], '0.12')

    def test_infrastructure_failure_excludes_grade_without_changing_original(self):
        save(self.run / 'U05/worker-state.json', {'status': 'infrastructure_error', 'reason': 'APIConnectionError'})
        stage = export_run(self.config, self.run, self.root / 'infrastructure-stage')
        case = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]
        self.assertEqual(case['core_acceptance'], 'unknown')
        self.assertFalse(case['valid_for_scoring'])
        self.assertEqual(case['automatic_verdict'], 'pass')
        self.assertEqual(case['infrastructure_error'], 'APIConnectionError')

    def test_completed_length_failure_retains_original_valid_failure(self):
        save(self.run / 'U05/worker-state.json', {'status': 'completed'})
        save(self.run / 'U05/result.json', {'id': 'U05', 'phases': [{'text': '', 'stop_reason': 'length'}]})
        save(self.run / 'U05/grade/grade.json', {'id': 'U05', 'verdict': 'fail', 'checks': {'report': {'value': 0}}})
        stage = export_run(self.config, self.run, self.root / 'length-stage')
        case = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]
        self.assertEqual(case['core_acceptance'], 'fail')
        self.assertTrue(case['valid_for_scoring'])

    def test_completed_recovery_keeps_prior_error_as_evidence_without_excluding_final_grade(self):
        save(self.run / 'U05/worker-state.json', {'status': 'completed', 'resume_count': 1})
        save(self.run / 'U05/runtime-error.json', {'type': 'PriorInterruption'})
        stage = export_run(self.config, self.run, self.root / 'recovered-stage')
        case = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]
        self.assertTrue(case['valid_for_scoring'])
        self.assertEqual(case['core_acceptance'], 'pass')
        self.assertTrue((stage / 'U05/runtime-error.json').exists())

    def test_grade_without_result_is_not_a_completed_execution(self):
        (self.run / 'U05/result.json').unlink()
        stage = export_run(self.config, self.run, self.root / 'missing-result-stage')
        case = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]
        self.assertEqual(case['core_acceptance'], 'unknown')
        self.assertFalse(case['valid_for_scoring'])
        self.assertFalse(case['run_complete'])
        self.assertEqual(case['automatic_verdict'], 'pass')

    def current_accounting(self, *, unknown=False):
        from formal20_coordinator import Coordinator
        (self.run / 'budget.json').unlink()
        coordinator = Coordinator(self.run, currency='CNY')
        coordinator.acquire('U05', 1, '1', {'payload': {'model': 'offline'}})
        first = coordinator.dispatch()[0]
        usage = {'prompt_tokens': 10, 'completion_tokens': 2}
        coordinator.settle(first['request_id'], usage, {'body': {'usage': usage}})
        # Settlement retry and the many journal snapshots must never double count.
        coordinator.settle(first['request_id'], usage, {'body': {'usage': usage}})
        coordinator.acquire('U05', 2, '1', {'payload': {'model': 'offline'}})
        second = coordinator.dispatch()[0]
        if unknown:
            coordinator.mark_unknown(second['request_id'], 'APIConnectionError')
        else:
            coordinator.settle(second['request_id'], {'prompt_tokens': 7, 'completion_tokens': 1}, {})
        return coordinator

    def test_export_aggregates_saved_usage_once_across_ledger_snapshots(self):
        coordinator = self.current_accounting()
        stage = export_run(self.config, self.run, self.root / 'usage-stage')
        run = json.loads((stage / 'run.json').read_text(encoding='utf-8'))
        metrics = run['cases'][0]['metrics']
        self.assertEqual((metrics['prompt_tokens'], metrics['completion_tokens']), (17, 3))
        self.assertEqual(metrics['model_requests'], 2)
        self.assertEqual(metrics['estimated_cny'], coordinator.snapshot()['estimated_cost_at_peak'])
        self.assertEqual((run['prompt_tokens'], run['completion_tokens']), (17, 3))

    def test_unknown_request_keeps_partial_usage_separate_from_total(self):
        self.current_accounting(unknown=True)
        stage = export_run(self.config, self.run, self.root / 'partial-usage-stage')
        metrics = json.loads((stage / 'run.json').read_text(encoding='utf-8'))['cases'][0]['metrics']
        self.assertIsNone(metrics['prompt_tokens'])
        self.assertIsNone(metrics['completion_tokens'])
        self.assertEqual(metrics['known_prompt_tokens'], 10)
        self.assertEqual(metrics['known_completion_tokens'], 2)
        self.assertEqual(metrics['unknown_requests'], 1)

    def test_completed_delivery_resume_preserves_final_table(self):
        result = finalize_run(self.config, self.run, self.api)
        control = Path(result['control_dir'])
        analysis = self.root / 'provided-analysis.json'
        save(analysis, {'summary': 'Final submitted analysis.', 'recommendations': [], 'case_explanations': []})
        submit_analysis_task(control, analysis, self.api)
        table = (control / '指标升降表.md').read_bytes()
        self.assertIn('Final submitted analysis.', table.decode('utf-8'))
        finalize_run(self.config, self.run, self.api)
        self.assertEqual((control / '指标升降表.md').read_bytes(), table)
        self.assertEqual(resume_delivery(control, self.api)['status'], 'delivery_complete')

    def test_submit_timeout_reuses_original_packet_request_and_delivery(self):
        result = finalize_run(self.config, self.run, self.api)
        control = Path(result['control_dir'])
        packet = (control / 'packet.json').read_bytes()
        save(control / 'analysis.json', {'summary': 'Offline protocol validation; no capability conclusion.', 'recommendations': [], 'case_explanations': []})
        endpoint = '/comparisons/' + result['comparison_id'] + '/review'
        self.api.lose_response = endpoint
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(control, control / 'analysis.json', self.api)
        request = (control / 'request.json').read_bytes()
        self.assertFalse((control / 'receipt.json').exists())
        done = submit_analysis_task(control, control / 'analysis.json', self.api)
        self.assertEqual(done['status'], 'delivery_complete')
        self.assertEqual((control / 'packet.json').read_bytes(), packet)
        self.assertEqual((control / 'request.json').read_bytes(), request)
        self.assertEqual(done['receipt']['delivery_id'], json.loads(packet)['delivery_id'])
        self.assertTrue((control / 'report.json').is_file())
        save(control / 'analysis.json', {'summary': 'changed input'})
        with self.assertRaises(ValueError):
            submit_analysis_task(control, control / 'analysis.json', self.api)


if __name__ == '__main__':
    unittest.main()
