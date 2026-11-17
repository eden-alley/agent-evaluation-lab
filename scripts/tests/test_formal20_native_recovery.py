"""Scripted-API validation of native multi-turn/checkpoint recovery, never paid API."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formal20_concurrent import run_batch
from formal20_coordinator import Coordinator
from formal20_runtime import (ScriptedAPI, ValidationBoundary, default_binding, execute_case,
                              inspect_run, load_cases, resume_run)

ROOT = Path(r'C:\Users\叶宸玮\Documents\Codex\2026-11-06\new-chat-5\outputs\real-path-validation-20261116')


class NativeRecoveryTests(unittest.TestCase):
    def run_validation(self, ids, scripts, **changes):
        ROOT.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix='native-recovery-', dir=ROOT)
        self.addCleanup(temp.cleanup)
        out = Path(temp.name) / 'run'
        config = {**default_binding(), 'backend': 'real', 'transport': 'scripted_api',
                  'validation': True, 'workers': 1, 'case_timeout': 120, 'budget_limit': '30',
                  'scripts_by_case': scripts, 'out': str(out), **changes}
        result = run_batch(config, load_cases(config, ids))
        if not result['complete'] and 'worker_error' in (result.get('halt') or ''):
            diagnostic={'summary':result,'runtime_errors':{},'error_events':{}}
            for cid in ids:
                error=out/cid/'runtime-error.json';events=out/cid/'events.jsonl'
                if error.exists():diagnostic['runtime_errors'][cid]=json.loads(error.read_text(encoding='utf-8'))
                if events.exists():diagnostic['error_events'][cid]=[e for e in map(json.loads,events.read_text(encoding='utf-8').splitlines()) if e.get('type') in ('error','checkpoint_error','checkpoint_failed')]
            (ROOT/('native-test-failure-'+uuid4().hex+'.json')).write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
        return result, out

    def test_native_multi_turn_and_summary_response_are_consumed(self):
        steps = ['第一轮验证结束。', '第二轮验证结束。', '第三轮验证结束。', '第四轮验证结束。',
                 '前四轮已经结束，保留用户要求和执行事实。', '第五轮验证结束。']
        result, out = self.run_validation(['O07'], {'O07': steps})
        phases = json.loads((out/'O07/phases.json').read_text(encoding='utf-8'))
        self.assertEqual([p['index'] for p in phases], [1, 2, 3, 4, 5], {'phases':phases,'halt':result['halt']})
        self.assertTrue(all(p['stop_reason'] == 'end_turn' for p in phases), phases)
        self.assertTrue(result['complete'], result['halt'])
        self.assertEqual(result['budget']['requests'], 6)
        self.assertEqual(result['budget']['response_count'], 6)
        pending = json.loads((out/'O07/response-state.json').read_text(encoding='utf-8'))
        self.assertTrue(pending['consumed'])
        requests = [json.loads(line) for line in (out/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
        summary_requests = [row for row in requests if row['kind'] == 'request'
                            and 'tools' not in row['payload']]
        self.assertEqual(len(summary_requests), 1)

    def test_resume_continues_remaining_native_turns_without_duplicate_response(self):
        steps = ['第一轮验证结束。', '第二轮验证结束。', '第三轮验证结束。', '第四轮验证结束。',
                 '前四轮已经结束，保留用户要求和执行事实。', '第五轮验证结束。']
        paused, out = self.run_validation(['O07'], {'O07': steps},
                                          interrupt_after_response=True, auto_resume_validation=False)
        self.assertEqual(paused['halt'], 'checkpoint_paused')
        config = json.loads((out/'config.json').read_text(encoding='utf-8'))
        resumed = resume_run(config, out)
        phases = json.loads((out/'O07/phases.json').read_text(encoding='utf-8'))
        self.assertEqual([p['index'] for p in phases], [1, 2, 3, 4, 5], phases)
        self.assertTrue(all(p['stop_reason'] == 'end_turn' for p in phases), phases)
        self.assertTrue(resumed['complete'], resumed['halt'])
        self.assertEqual(resumed['budget']['requests'], 6)
        self.assertEqual(json.loads((out/'O07/api-script-state.json').read_text())['cursor'], 6)

    def test_native_binding_corruption_refuses_before_resume_changes_any_file(self):
        paused, out = self.run_validation(['U05', 'U04'], {'U05': ['验证结束。'], 'U04': ['验证结束。']},
                                          interrupt_after_response=True, auto_resume_validation=False)
        self.assertEqual(paused['halt'], 'checkpoint_paused')
        checkpoint = out/'U05/checkpoint/default.json'
        native = json.loads(checkpoint.read_text(encoding='utf-8'))
        native['binding']['limits']['max_steps'] += 1
        checkpoint.write_text(json.dumps(native, ensure_ascii=False), encoding='utf-8')
        config = json.loads((out/'config.json').read_text(encoding='utf-8'))
        before = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob('*') if p.is_file()}
        self.assertEqual(inspect_run(out)['status'], 'needs_recovery')
        with self.assertRaisesRegex(ValueError, 'needs_recovery'):
            resume_run(config, out)
        self.assertEqual(before, {str(p.relative_to(out)): p.read_bytes() for p in out.rglob('*') if p.is_file()})
        self.assertFalse((out/'U04/workspace').exists())

    def test_native_schema_and_verifier_limits_are_rejected_in_preflight(self):
        paused, out = self.run_validation(['U05'], {'U05': ['验证结束。']},
                                          interrupt_after_response=True, auto_resume_validation=False)
        self.assertEqual(paused['halt'], 'checkpoint_paused')
        checkpoint = out/'U05/checkpoint/default.json'
        original = json.loads(checkpoint.read_text(encoding='utf-8'))
        for alteration in ('schema', 'verifier'):
            with self.subTest(alteration=alteration):
                native = json.loads(json.dumps(original))
                if alteration == 'schema':
                    native['schema_version'] = 999
                else:
                    native['run_state']['requires_verifier'] = True
                checkpoint.write_text(json.dumps(native, ensure_ascii=False), encoding='utf-8')
                self.assertEqual(inspect_run(out)['status'], 'needs_recovery')

    def test_missing_response_identity_refuses_before_any_resend(self):
        paused,out=self.run_validation(['U05'],{'U05':['验证结束。']},
            interrupt_after_response=True,auto_resume_validation=False)
        self.assertEqual(paused['halt'],'checkpoint_paused')
        (out/'U05/response-state.json').unlink()
        cfg=json.loads((out/'config.json').read_text(encoding='utf-8'))
        before=(out/'request-ledger.jsonl').read_bytes()
        self.assertEqual(inspect_run(out)['status'],'needs_recovery')
        with self.assertRaisesRegex(ValueError,'needs_recovery'):resume_run(cfg,out)
        self.assertEqual(before,(out/'request-ledger.jsonl').read_bytes())
        self.assertEqual(json.loads((out/'U05/api-script-state.json').read_text())['cursor'],1)

    def test_native_recorded_checkpoint_write_failure_is_infrastructure_error(self):
        ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='native-storage-fault-', dir=ROOT) as temp:
            out=Path(temp)/'run';folder=out/'U05';folder.mkdir(parents=True)
            config={**default_binding(),'transport':'scripted_api','validation':True}
            coordinator=Coordinator(out,budget_limit='30')
            class Connection:
                def send(self,message):
                    op=message['op']
                    if op=='next_attempt':self.reply={'attempt_id':coordinator.next_attempt('U05')}
                    elif op=='acquire':
                        coordinator.acquire('U05',message['attempt_id'],message['reserve_cost'],message['prompt_metadata'])
                        self.reply=coordinator.dispatch()[0]
                    elif op=='settle':self.reply=coordinator.settle(message['request_id'],message['usage'],message['response_metadata'])
                    elif op=='consumed':self.reply=coordinator.register_consumed(message['request_id'])
                    else:raise AssertionError('Unexpected RPC '+op)
                def recv(self):return self.reply
            original_replace=os.replace
            def fail_recorded_replace(source,target,*args,**kwargs):
                if Path(target)==folder/'checkpoint/default.json':
                    native=json.loads(Path(source).read_text(encoding='utf-8'))
                    if any(record['status']=='recorded' for record in native['run_state']['call_records'].values()):
                        raise PermissionError('injected native checkpoint storage failure')
                return original_replace(source,target,*args,**kwargs)
            script=[{'tool':'write_file','arguments':{'path':'validation-receipt.txt','content':'written-once'}},'end']
            with ValidationBoundary(), patch('os.replace',side_effect=fail_recorded_replace):
                with self.assertRaisesRegex(RuntimeError,'needs_recovery:checkpoint_storage_failure'):
                    execute_case(config,load_cases(config,['U05'])[0],out,
                                 ScriptedAPI(script,folder,config['model']),Connection())
            self.assertEqual((folder/'workspace/validation-receipt.txt').read_text(),'written-once')
            self.assertFalse((folder/'grade/grade.json').exists())
            self.assertEqual(coordinator.snapshot()['requests'],1)
            native=json.loads((folder/'checkpoint/default.json').read_text(encoding='utf-8'))
            self.assertTrue(any(r['status']=='executing' for r in native['run_state']['call_records'].values()))


if __name__ == '__main__':
    unittest.main()
