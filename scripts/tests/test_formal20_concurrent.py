"""Synthetic process tests; never execute the original tasks, models or scorers."""
import json
from hashlib import sha256
import multiprocessing as mp
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formal20_concurrent import run_batch, synthetic_cases
from formal20_worker import OfflineBoundary, run_legacy_probe, worker_main
from formal20_coordinator import Coordinator


class ProcessTests(unittest.TestCase):
    def run_sim(self, n, cases=None, **options):
        temp = tempfile.TemporaryDirectory(prefix='formal20-sim-')
        self.addCleanup(temp.cleanup)
        config = dict(out=Path(temp.name)/'run', workers=n, start_barrier=True,
                      case_timeout=5, request_interval=0)
        config.update(options)
        result = run_batch(config, cases or synthetic_cases(20))
        self.assertEqual(result['mode'], 'offline_simulation')
        self.assertFalse((config['out']/'run.json').exists())
        return result, config['out']

    def test_configured_process_limit_and_overlap(self):
        baseline = None
        for n in (1, 2, 4, 8):
            with self.subTest(workers=n):
                result, out = self.run_sim(n)
                self.assertTrue(result['complete'], result.get('halt'))
                self.assertEqual(result['metrics']['max_active_cases'], n)
                self.assertLessEqual(result['budget']['max_observed_inflight'], n)
                self.assertEqual(result['budget']['requests'], 40)
                self.assertEqual(result['budget']['response_count'], 40)
                self.assertEqual([c['id'] for c in result['cases']], [c['id'] for c in synthetic_cases(20)])
                ends = []
                for case in result['cases']:
                    workspace = out/case['id']/'workspace'
                    value = json.loads((workspace/'result.json').read_text(encoding='utf-8'))
                    self.assertEqual(value['owner'], case['id'])
                    self.assertEqual(value['process_marker'], case['id'])
                    self.assertEqual(value['steps'], [1, 2])
                    ends.append(case['ended_at'])
                    self.assertNotEqual(case['pid'], os.getpid())
                first = result['cases'][:n]
                self.assertEqual(len({c['pid'] for c in first}), n)
                self.assertLessEqual(max(c['started_at'] for c in first), min(c['ended_at'] for c in first))
                self.assertGreaterEqual(result['cases'][n]['started_at'], min(c['ended_at'] for c in first))
                comparable = (result['budget']['requests'], result['budget']['estimated_cost_at_peak'])
                baseline = comparable if baseline is None else baseline
                self.assertEqual(comparable, baseline)

    def test_worker_count_and_request_cap_are_independent(self):
        result, _ = self.run_sim(8, max_inflight_requests=2)
        self.assertEqual(result['metrics']['max_active_cases'], 8)
        self.assertEqual(result['budget']['max_observed_inflight'], 2)
        self.assertEqual(result['budget']['response_count'], 40)

    def test_global_budget_and_rate_matrix(self):
        for n in (1,2,4,8):
            with self.subTest(workers=n):
                cases=synthetic_cases(2)
                for case in cases: case.update(reserve_cost='6',kind='one_request')
                result,_=self.run_sim(n,cases,budget_limit='10',prompt_price_per_million='20000',output_price_per_million='0')
                self.assertTrue(result['complete'])
                self.assertEqual(result['budget']['requests'],2)
                self.assertEqual(result['budget']['estimated_cost_at_peak'],'4')
                self.assertEqual(float(result['budget']['reserved_total']),0)
                self.assertEqual(result['budget']['max_observed_inflight'],1)
                result,out=self.run_sim(n,synthetic_cases(n+1),request_interval=.015)
                requests=[json.loads(line) for line in (out/'requests.jsonl').read_text().splitlines()]
                times=[r['monotonic_time'] for r in requests if r['kind']=='request']
                self.assertTrue(all(b-a>=.015 for a,b in zip(times,times[1:])))

    def test_partial_request_limit_is_not_agent_failure(self):
        result,_=self.run_sim(2,synthetic_cases(5),max_requests=2)
        self.assertEqual(result['budget']['requests'],2)
        self.assertEqual(result['budget']['response_count'],2)
        self.assertFalse(result['complete'])
        self.assertGreater(result['counts'].get('not_run',0),0)
        result,_=self.run_sim(2,synthetic_cases(3),max_requests_per_case=1)
        self.assertEqual(result['counts'],{'case_limit':3})
        self.assertIsNone(result['halt'])

    def test_waiting_for_global_rate_is_not_request_timeout(self):
        cases=synthetic_cases(2)
        for c in cases: c.update(kind='one_request',delay=.01)
        result,_=self.run_sim(2,cases,request_interval=.3,timeout_after_ready=.1)
        self.assertTrue(result['complete'],result['halt'])

    def test_ledger_failure_drains_responses_and_leaves_no_workers(self):
        original=Coordinator._persist
        def failing(owner):
            if owner.snapshot()['response_count']>=1: raise OSError('synthetic ledger failure')
            return original(owner)
        cases=synthetic_cases(4)
        cases[0]['delay']=.02
        cases[1]['delay']=.08
        try:
            with patch.object(Coordinator,'_persist',failing):
                result,_=self.run_sim(2,cases)
            self.assertFalse(result['complete'])
            self.assertEqual(result['budget']['response_count'],2)
            self.assertEqual(result['budget']['requests'],2)
            self.assertFalse(result['budget_persisted'])
            self.assertFalse(mp.active_children())
        finally:
            for child in mp.active_children():
                child.kill(); child.join(2)

    def test_reservation_write_failure_cleans_all_processes(self):
        original=Coordinator._persist
        def failing(owner):
            if owner.snapshot()['requests']>=1: raise OSError('synthetic reservation failure')
            return original(owner)
        try:
            with patch.object(Coordinator,'_persist',failing):
                result,_=self.run_sim(2,synthetic_cases(4))
            self.assertFalse(result['complete'])
            self.assertEqual(result['budget']['response_count'],0)
            self.assertFalse(result['budget_persisted'])
            self.assertFalse(mp.active_children())
        finally:
            for child in mp.active_children(): child.kill();child.join(2)

    def test_closed_worker_pipe_stops_actual_dispatch(self):
        for n in (1,2,4,8):
            cases=synthetic_cases(n+1)
            cases[0]['kind']='disconnect'
            result,_=self.run_sim(n,cases,timeout_after_ready=.3)
            self.assertFalse(result['complete'])
            self.assertEqual(result['halt'],'worker_pipe_disconnected')
            self.assertEqual(len(result['budget']['unknown_requests']),1)

    def test_legacy_adapter_delegates_only_to_synthetic_probe(self):
        text = '''from types import SimpleNamespace
from decimal import Decimal
OFFLINE_PROBE=True
PARAMS={'model':'offline-scripted','adapter_body':{},'request_body':{},'max_tokens':12}
def cost(prompt,output): return Decimal('0.006')
def execute_case(case,suite,run,client):
    guard=RequestGuard(client,run,case['id'])
    response=guard.chat.completions.create(model='offline-scripted',extra_body={},messages=[])
    return {'verdict':'probe_only','checks':{'delegated':True}}
'''
        with tempfile.TemporaryDirectory() as temp:
            entry=Path(temp)/'synthetic_entry.py';entry.write_text(text,encoding='utf-8')
            cases=synthetic_cases(1)
            cases[0].update(kind='legacy_probe',source_entry=str(entry),source_sha256=sha256(entry.read_bytes()).hexdigest())
            result,_=self.run_sim(1,cases)
            self.assertTrue(result['complete'],result['halt'])
            self.assertEqual(result['cases'][0]['result']['verdict'],'probe_only')
            self.assertEqual(result['budget']['requests'],1)
            self.assertEqual(result['budget']['response_count'],1)
            cases[0]['probe_response_model']='wrong-model'
            result,_=self.run_sim(1,cases)
            self.assertFalse(result['complete'])
            self.assertEqual(result['halt'],'response_model_mismatch')
        with self.assertRaises(PermissionError):
            run_legacy_probe('run-formal-current.py','unused',{'id':'SIM-1'},'.','.',None,None)

    def test_errors_stop_dispatch_and_drain_inflight(self):
        for n in (1, 2, 4, 8):
            with self.subTest(workers=n):
                cases = synthetic_cases(n+2)
                cases[0].update(kind='api_error', delay=.08)
                for case in cases[1:]: case['delay'] = .16
                result, _ = self.run_sim(n, cases)
                self.assertFalse(result['complete'])
                self.assertEqual(result['retries'], 0)
                self.assertEqual(len(result['budget']['unknown_requests']), 1)
                self.assertGreater(float(result['budget']['reserved_total']), 0)
                self.assertEqual(result['budget']['response_count'], n-1)
                self.assertTrue(all(c['status']=='not_run' for c in result['cases'][n:]))
                self.assertEqual(result['budget']['requests'], n)

    def test_death_timeout_and_unexpected_exit(self):
        for n in (1, 2, 4, 8):
            for kind in ('crash', 'timeout', 'unexpected_checkpoint', 'unknown_usage'):
                with self.subTest(workers=n, kind=kind):
                    cases = synthetic_cases(n+1)
                    cases[0]['kind'] = kind
                    result, _ = self.run_sim(n, cases, timeout_after_ready=.25)
                    self.assertFalse(result['complete'])
                    self.assertIsNotNone(result['halt'])
                    self.assertEqual(result['retries'], 0)
                    self.assertTrue(all(c.get('resume_count',0)==0 for c in result['cases']))

    def test_checkpoint_keeps_workspace_budget_and_one_write(self):
        for n in (1, 2, 4, 8):
            with self.subTest(workers=n):
                cases = synthetic_cases(n+1)
                cases[0]['kind'] = 'checkpoint'
                result, out = self.run_sim(n, cases)
                self.assertTrue(result['complete'], result['halt'])
                first = result['cases'][0]
                self.assertEqual(first['resume_count'], 1)
                self.assertEqual(len(first['processes']), 2)
                self.assertEqual((out/first['id']/'workspace/receipt.txt').read_text(), 'recorded-once')
                self.assertEqual(result['budget']['per_case'][first['id']], 2)
                self.assertEqual(json.loads((out/first['id']/'workspace/result.json').read_text())['receipt_writes'], 1)

    def test_halt_blocks_checkpoint_resume(self):
        for n in (1, 2, 4, 8):
            with self.subTest(workers=n):
                cases = synthetic_cases(n+1)
                cases[0].update(kind='checkpoint', pause_before_exit=.12, halt_at_checkpoint=True)
                result, _ = self.run_sim(n, cases)
                self.assertFalse(result['complete'])
                self.assertEqual(result['cases'][0]['resume_count'], 0)

    def test_bad_config_and_existing_output_are_rejected(self):
        for workers in (0, -1, 1.5, True, '2'):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                self.run_sim(workers)
        for cap in (0, -1, 1.5, True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.run_sim(2, max_inflight_requests=cap)
        cases = synthetic_cases(2); cases[1]['id'] = cases[0]['id']
        with self.assertRaises(ValueError): self.run_sim(2, cases)
        result, out = self.run_sim(8, synthetic_cases(1))
        self.assertEqual(result['metrics']['max_active_cases'], 1)
        with self.assertRaises(FileExistsError): run_batch(dict(out=out,workers=2), synthetic_cases(2))

    def test_offline_boundary_blocks_network_credentials_and_models(self):
        import socket
        with OfflineBoundary():
            with self.assertRaises(PermissionError): socket.socket()
            with self.assertRaises(PermissionError): os.getenv('DASHSCOPE_API_KEY')
            with self.assertRaises(PermissionError): __import__('openai')
            with self.assertRaises(PermissionError): __import__('grade-calibration')

    def test_disconnected_coordinator_stops_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            parent, child = mp.get_context('spawn').Pipe()
            case=synthetic_cases(1)[0]
            process = mp.get_context('spawn').Process(target=worker_main,args=(case,temp,child))
            process.start(); child.close()
            self.assertTrue(parent.poll(10)); self.assertEqual(parent.recv()['op'],'ready')
            parent.send({'status':'start'})
            self.assertTrue(parent.poll(10)); self.assertEqual(parent.recv()['op'],'acquire');parent.close()
            process.join(5)
            if process.is_alive(): process.terminate(); process.join()
            self.assertEqual(process.exitcode, 0)
            self.assertFalse((Path(temp)/case['id']/'workspace/result.json').exists())
            self.assertIn('EOFError',(Path(temp)/case['id']/'events.jsonl').read_text())


if __name__ == '__main__': unittest.main()
