"""One approval/one run identity across public starts; no Agent or model calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from hashlib import sha256
import importlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
import formal20_concurrent as concurrent
from formal20_runtime import default_binding, freeze_plan, load_cases


class ReadOnlyPlatform:
    def __init__(self, workflow, data_root): self.workflow = workflow; self.data_root = data_root
    def request(self, method, path, **kwargs):
        if method != 'GET': raise AssertionError('Start preflight must be read-only')
        if path == '/health': return {'capabilities': {'comparison_statistics_snapshot': True},
            'storage': {'data_root': str(self.data_root),
                        'evaluation_runs_root': str(self.data_root / 'evaluation-runs')}}
        if path == '/projects/test-project': return {'id': 'test-project'}
        if path == '/skills/test-skill/content': return {'version': {'content_hash': self.workflow['content_hash']}}
        raise AssertionError(path)
    def close(self): pass


class StartGuardTests(unittest.TestCase):
    def setUp(self):
        self.daily = importlib.import_module('evaluation')
        self.temp = tempfile.TemporaryDirectory(prefix='execution-start-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        entry, _ = self.daily.method_entry()
        self.workflow = {'skill_id': 'test-skill', 'version_id': 'test-version',
                         'content_hash': entry['platform_content_hash']}
        self.api = ReadOnlyPlatform(self.workflow, self.root / 'platform')

    def plan(self, name, *, workers=1, validation=False, control=None, run_id='one-run-id'):
        delivery = {'api_url': 'http://127.0.0.1:0', 'data_root': str(self.root / 'platform'),
            'archive_root': str(self.root / 'archives'), 'run_id': run_id,
            'project_id': 'test-project', 'project_name': 'test project', 'name': name,
            'version': default_binding()['harness_version'], 'workflow': self.workflow}
        if control is not None: delivery['control_dir'] = str(control)
        config = {**default_binding(), 'backend': 'real', 'validation': validation,
            'transport': 'scripted_api' if validation else 'provider_api',
            'baseline_only': True, 'workers': workers, 'case_ids': ['U05'], 'delivery': delivery}
        path = self.root / (name + '.json')
        approved = freeze_plan(config, path)
        config = json.loads(path.read_text(encoding='utf-8'))
        config.update(plan_file=str(path), approved_plan_sha256=None if validation else approved)
        return config, path, approved

    def test_consumed_daily_approval_is_rejected_by_raw_execute_before_dispatch(self):
        config, plan, approved = self.plan('consumed')
        record = self.daily.claim_provider_plan(config, self.root / 'original')
        original = Path(record).read_bytes()
        out = self.root / 'raw-second'
        argv = ['runner', 'execute', '--plan', str(plan), '--transport', 'provider_api',
                '--approved-plan-sha256', approved, '--out', str(out)]
        with patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()), \
             patch.object(self.daily, 'Client', return_value=self.api), \
             patch.object(concurrent, 'run_batch', side_effect=AssertionError('dispatch reached')):
            with self.assertRaises(PermissionError): concurrent.main()
        self.assertFalse(out.exists())
        self.assertEqual(Path(record).read_bytes(), original)

    def test_direct_run_batch_cannot_bypass_consumed_approval(self):
        config, _, _ = self.plan('direct')
        self.daily.claim_provider_plan(config, self.root / 'original')
        out = self.root / 'direct-second'
        with patch.object(concurrent, '_run', side_effect=AssertionError('worker path reached')):
            with self.assertRaises(PermissionError):
                concurrent.run_batch({**config, 'out': str(out)}, load_cases(config, ['U05']))
        self.assertFalse(out.exists())

    def test_different_approved_plans_cannot_start_same_unarchived_run(self):
        first, first_plan, first_sha = self.plan('first')
        second, second_plan, second_sha = self.plan('second', workers=2)
        def stopped(config, cases):
            out = Path(config['out']); out.mkdir()
            return {'config': config, 'complete': False, 'halt': 'probe_before_execution'}
        with patch.object(self.daily, 'run_batch', stopped):
            self.daily.start_evaluation(first, self.root / 'first-run', api=self.api,
                plan_path=first_plan, approved_sha=first_sha)
            with self.assertRaises(PermissionError):
                self.daily.start_evaluation(second, self.root / 'second-run', api=self.api,
                    plan_path=second_plan, approved_sha=second_sha)
        self.assertFalse((self.root / 'second-run').exists())
        self.assertFalse((self.root / 'platform/execution-approvals' / (second_sha + '.json')).exists())
        self.assertFalse((self.root / 'archives/one-run-id').exists())

    def test_atomic_same_run_id_reservation_has_one_winner_without_spending_loser(self):
        plans = [self.plan('race-first'), self.plan('race-second', workers=2)]
        barrier = threading.Barrier(2)
        def claim(item):
            index, (config, _, approved) = item
            barrier.wait()
            try:
                return index, self.daily.claim_provider_plan(config, self.root / ('race-' + str(index)))
            except PermissionError:
                return index, None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, enumerate(plans)))
        winners = [index for index, record in results if record]
        self.assertEqual(len(winners), 1, results)
        loser = 1 - winners[0]
        self.assertFalse((self.root / 'platform/execution-approvals' / (plans[loser][2] + '.json')).exists())

    def test_scripted_daily_start_also_reserves_the_unarchived_run_id(self):
        first, _, _ = self.plan('scripted-first', validation=True)
        second, _, _ = self.plan('scripted-second', validation=True)
        def stopped(config, cases):
            Path(config['out']).mkdir()
            return {'config': config, 'complete': False, 'halt': 'probe_before_execution'}
        with patch.object(self.daily, 'run_batch', stopped):
            self.daily.start_evaluation(first, self.root / 'scripted-first-run', api=self.api)
            with self.assertRaises(PermissionError):
                self.daily.start_evaluation(second, self.root / 'scripted-second-run', api=self.api)
        self.assertFalse((self.root / 'scripted-second-run').exists())

    def test_raw_execute_validates_delivery_paths_before_claim(self):
        _, plan, approved = self.plan('raw-overlap', control=self.root / 'archives/control')
        out = self.root / 'raw-overlap-run'
        argv = ['runner', 'execute', '--plan', str(plan), '--transport', 'provider_api',
                '--approved-plan-sha256', approved, '--out', str(out)]
        with patch.object(sys, 'argv', argv), patch.object(self.daily, 'Client', return_value=self.api), \
             patch('formal20_start_guard.claim_start', side_effect=AssertionError('approval consumed')):
            with self.assertRaises(ValueError): concurrent.main()
        self.assertFalse(out.exists())
        self.assertFalse((self.root / 'platform/execution-approvals').exists())

    def test_original_provider_resume_keeps_reservation_and_existing_budget(self):
        config, _, _ = self.plan('resume-original')
        out = self.root / 'original-run'
        def no_workers(config, cases, directory, timeout):
            budget = directory / 'budget.json'
            if not budget.exists(): budget.write_bytes(b'{"requests":7,"spent":"1.25"}')
            return {'config': config, 'complete': False, 'halt': 'checkpoint_paused'}
        with patch.object(concurrent, '_run', no_workers):
            initial = concurrent.run_batch({**config, 'out': str(out)}, load_cases(config, ['U05']))
            saved = initial['config']
            receipt = Path(saved['execution_start_record'])
            receipt_before = receipt.read_bytes(); budget_before = (out / 'budget.json').read_bytes()
            from formal20_runtime import resume_run
            with patch('formal20_runtime.inspect_run', return_value={'status': 'checkpoint_paused'}):
                resumed = resume_run(saved, out)
            self.assertTrue(resumed['config']['_resume'])
            self.assertEqual(receipt.read_bytes(), receipt_before)
            self.assertEqual((out / 'budget.json').read_bytes(), budget_before)
            with self.assertRaises(PermissionError):
                concurrent.run_batch({**saved, 'out': str(self.root / 'different-output')}, load_cases(saved, ['U05']))
        self.assertFalse((self.root / 'different-output').exists())

    def test_pre_guard_approval_receipt_still_blocks_new_plan_with_same_run_id(self):
        config, _, approved = self.plan('legacy-used')
        directory = self.root / 'platform/execution-approvals'; directory.mkdir(parents=True)
        receipt = directory / (approved + '.json')
        previous = {'plan_sha256': approved, 'plan_file': config['plan_file'],
                    'run_id': 'one-run-id', 'out': str(self.root / 'legacy-original')}
        receipt.write_text(json.dumps(previous), encoding='utf-8')
        before = receipt.read_bytes()
        second, _, second_sha = self.plan('after-upgrade', workers=2)
        with self.assertRaises(PermissionError): self.daily.claim_provider_plan(second, self.root / 'new-output')
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse((directory / (second_sha + '.json')).exists())

    def test_started_reservation_cannot_create_fresh_budget_if_original_output_is_moved(self):
        config, _, _ = self.plan('used-reservation')
        out = self.root / 'original-run'
        def no_workers(config, cases, directory, timeout): return {'config': config}
        with patch.object(concurrent, '_run', no_workers):
            initial = concurrent.run_batch({**config, 'out': str(out)}, load_cases(config, ['U05']))
            preserved = self.root / 'original-preserved'; out.rename(preserved)
            with self.assertRaises(PermissionError):
                concurrent.run_batch(initial['config'], load_cases(config, ['U05']))
        self.assertTrue((preserved / 'config.json').exists())
        self.assertFalse(out.exists())

    def test_reserved_receipt_cannot_be_presented_as_a_started_resume(self):
        config, _, _ = self.plan('reserved-only')
        out = self.root / 'not-started'
        receipt = self.daily.claim_provider_plan(config, out)
        config = {**config, 'out': str(out), 'approval_record': receipt}
        out.mkdir(); (out / 'config.json').write_text(json.dumps(config), encoding='utf-8')
        with patch.object(concurrent, '_run', side_effect=AssertionError('worker path reached')):
            with self.assertRaises(PermissionError):
                concurrent.run_batch({**config, '_resume': True}, load_cases(config, ['U05']))
        self.assertFalse((out / 'budget.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows paths identify case-only run IDs as the same destination')
    def test_windows_case_only_run_id_cannot_start_a_second_run(self):
        first, _, _ = self.plan('upper-case', run_id='Daily-Run')
        second, _, approved = self.plan('lower-case', workers=2, run_id='daily-run')
        self.daily.claim_provider_plan(first, self.root / 'first-output')
        with self.assertRaises(PermissionError): self.daily.claim_provider_plan(second, self.root / 'second-output')
        self.assertFalse((self.root / 'platform/execution-approvals' / (approved + '.json')).exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows directory naming rules')
    def test_raw_guard_refuses_trailing_dot_and_reserved_directory_names(self):
        from formal20_start_guard import claim_start
        for index, name in enumerate(('Daily-Run.', 'NUL', 'con.json', 'COM1')):
            config, _, _ = self.plan('invalid-name-'+str(index), run_id=name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                claim_start(config, self.root/('invalid-out-'+str(index)))
        self.assertFalse((self.root/'platform/execution-approvals').exists())

    def test_two_concurrent_resumes_cannot_dispatch_against_the_same_saved_budget(self):
        config, _, _ = self.plan('resume-exclusivity')
        out = self.root / 'resume-run'; entered = threading.Event(); release = threading.Event()
        resumes = []
        def no_workers(config, cases, directory, timeout):
            if config.get('_resume'):
                resumes.append(str(directory))
                if len(resumes) == 1:
                    entered.set()
                    if not release.wait(20): raise AssertionError('test did not release first resume')
            return {'config': config, 'complete': False, 'halt': 'checkpoint_paused'}
        from formal20_runtime import resume_run
        with patch.object(concurrent, '_run', no_workers), \
             patch('formal20_runtime.inspect_run', return_value={'status': 'checkpoint_paused'}):
            initial = concurrent.run_batch({**config, 'out': str(out)}, load_cases(config, ['U05']))
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(resume_run, initial['config'], out)
                self.assertTrue(entered.wait(10), 'first resume did not reach the dispatcher')
                try:
                    with self.assertRaises(PermissionError): resume_run(initial['config'], out)
                finally:
                    release.set()
                first.result(timeout=10)
        self.assertEqual(len(resumes), 1)

    def test_process_exit_releases_execution_lock_without_deleting_its_file(self):
        from formal20_start_guard import execution_lock
        out = self.root / 'locked-run'; ready = self.root / 'ready'
        code = ("import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                "from formal20_start_guard import execution_lock\n"
                "with execution_lock(sys.argv[2]):\n"
                " Path(sys.argv[3]).write_text('locked'); sys.stdin.read()\n")
        # The Windows venv executable may be a launcher. Terminate the actual
        # stdlib-only interpreter that owns the OS lock, then wait for its exit.
        interpreter = getattr(sys, '_base_executable', sys.executable)
        child = subprocess.Popen([interpreter, '-B', '-c', code, str(ROOT / 'scripts'), str(out), str(ready)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline: time.sleep(.01)
            self.assertTrue(ready.exists(), 'lock holder failed to start')
            with self.assertRaises(PermissionError):
                with execution_lock(out): self.fail('another process owns this run')
        finally:
            if child.poll() is None: child.terminate()
            child.wait(timeout=10)
            child.stdin.close(); child.stderr.close()
        with execution_lock(out):
            self.assertTrue(ready.exists())


if __name__ == '__main__': unittest.main()
