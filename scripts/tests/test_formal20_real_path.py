"""Real frozen tasks/Agent/tools/scorers, scripted SDK only, isolated outputs."""
from hashlib import sha256
import json
import multiprocessing as mp
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from formal20_runtime import default_binding, load_cases, inspect_run,resume_run,freeze_plan,validate_binding,BASE,ENTRY
from formal20_concurrent import run_batch

ROOT=Path(r'C:\Users\叶宸玮\Documents\Codex\2026-11-06\new-chat-5\outputs\real-path-validation-20261116')


def run_real(ids,**changes):
    ROOT.mkdir(parents=True,exist_ok=True)
    temp=tempfile.TemporaryDirectory(prefix='integration-',dir=ROOT)
    config={**default_binding(),'backend':'real','transport':'scripted_api','validation':True,
        'workers':2,'out':str(Path(temp.name)/'run'),'case_timeout':120,'budget_limit':'30',
        'scripts_by_case':{cid:[{'tool':'read_file','arguments':{'path':'README.md'}},'集成验证结束；不作为正式成绩。'] for cid in ids},**changes}
    return temp,run_batch(config,load_cases(config,ids)),Path(config['out'])


class RealPathTests(unittest.TestCase):
    def test_parent_does_not_poll_checkpoint_while_native_worker_writes(self):
        original=Path.read_text
        def checked(path,*args,**kwargs):
            if path.name=='default.json' and path.parent.name=='checkpoint' and any(p.is_alive() for p in mp.active_children()):
                raise AssertionError('Parent reads a checkpoint while its worker is still active')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',checked):
            temp,result,out=run_real(['U05'],workers=1,scripts_by_case={'U05':['验证结束。']})
            self.addCleanup(temp.cleanup)
        self.assertTrue(result['complete'],result['halt'])

    def test_real_case_path_uses_original_agent_tools_and_grader(self):
        script=[{'tool':'read_file','arguments':{'path':'cli.py'}},
                {'tool':'run_shell','arguments':{'command':'echo validation-native','timeout':30}},'集成验证完成。']
        temp,result,out=run_real(['U05'],workers=1,scripts_by_case={'U05':script})
        self.addCleanup(temp.cleanup)
        self.assertTrue(result['complete'],result['halt'])
        self.assertEqual(result['mode'],'integration_validation')
        original=json.loads((out/'U05/result.json').read_text(encoding='utf-8'))
        self.assertIn('source_hashes',original)
        self.assertNotIn('status',original)
        self.assertTrue((out/'U05/worker-state.json').is_file())
        grade=json.loads((out/'U05/grade/grade.json').read_text(encoding='utf-8'))
        self.assertIn('checks',grade)
        self.assertNotEqual(grade.get('verdict'),'probe_only')
        trace=[json.loads(line) for line in (out/'U05/events.jsonl').read_text(encoding='utf-8').splitlines()]
        native=[e for e in trace if e['type']=='tool_result' and e.get('tool')=='run_shell']
        self.assertEqual(native[0].get('exit_code'),0,native)
        self.assertIn('validation-native',str(native[0]))
        binding=json.loads((out/'U05/runtime-binding.json').read_text(encoding='utf-8'))
        self.assertIn('source/agent.py',binding['agent_file'].replace('\\','/'))
        self.assertEqual(binding['grade_sha256_before'],binding['grade_sha256_after'])
        self.assertEqual(result['real_model_calls'],0)

    def test_real_recorded_checkpoint_and_saved_response_resume(self):
        for mode,cid in [('checkpoint','O08'),('response','U05')]:
            with self.subTest(mode=mode):
                steps=([{'tool':'write_file','arguments':{'path':'receipt.txt','content':'EXPENSE-OCT-STARTED'}},'验证结束。']
                       if cid=='O08' else [{'tool':'read_file','arguments':{'path':'cli.py'}},'验证结束。'])
                temp,result,out=run_real([cid],workers=1,scripts_by_case={cid:steps},
                    native_checkpoint_interrupt=mode=='checkpoint',interrupt_after_response=mode=='response')
                self.addCleanup(temp.cleanup)
                self.assertTrue(result['complete'],result['halt'])
                self.assertEqual(result['cases'][0]['resume_count'],1)
                self.assertEqual(result['budget']['per_case'][cid],2)
                trace=[json.loads(line) for line in (out/cid/'events.jsonl').read_text(encoding='utf-8').splitlines()]
                if cid=='O08':
                    writes=[e for e in trace if e['type']=='tool_result' and e.get('tool')=='write_file']
                    self.assertEqual(len(writes),1)
                    self.assertEqual((out/cid/'workspace/receipt.txt').read_text(),'EXPENSE-OCT-STARTED')
                self.assertTrue((out/cid/'checkpoint/default.json').exists())
                self.assertEqual(inspect_run(out)['status'],'finished')

    def test_fake_transport_exhaustion_has_no_real_fallback(self):
        temp,result,out=run_real(['U05'],workers=1,scripts_by_case={'U05':[]})
        self.addCleanup(temp.cleanup)
        self.assertFalse(result['complete'])
        self.assertTrue(result['halt'])
        self.assertEqual(result['real_model_calls'],0)

    def test_checkpoint_pause_resumes_existing_ledger(self):
        steps=[{'tool':'read_file','arguments':{'path':'cli.py'}},'验证结束。']
        temp,result,out=run_real(['U05'],workers=1,scripts_by_case={'U05':steps},
            interrupt_after_response=True,auto_resume_validation=False)
        self.addCleanup(temp.cleanup)
        self.assertEqual(result['halt'],'checkpoint_paused')
        self.assertEqual(inspect_run(out)['status'],'checkpoint_paused')
        cfg=json.loads((out/'config.json').read_text(encoding='utf-8'))
        resumed=resume_run(cfg,out)
        self.assertTrue(resumed['complete'],resumed['halt'])
        self.assertEqual(resumed['budget']['requests'],2)
        self.assertEqual(resumed['budget']['response_count'],2)
        self.assertEqual(json.loads((out/'U05/api-script-state.json').read_text())['cursor'],2)
        with self.assertRaisesRegex(ValueError,'binding'):
            resume_run({**cfg,'workers':8},out)

    def test_explicit_retry_preserves_unknown_fee(self):
        steps=[{'error':{'type':'RateLimitError','status_code':429,'provider_request_id':'validation-id','retry_after':'0'}},'验证结束。']
        temp,result,out=run_real(['U05'],workers=1,scripts_by_case={'U05':steps},max_retries=1)
        self.addCleanup(temp.cleanup)
        self.assertTrue(result['complete'],result['halt'])
        self.assertEqual(result['budget']['requests'],2)
        self.assertEqual(len(result['budget']['unknown_requests']),1)
        self.assertGreater(float(result['budget']['reserved_total']),0)
        self.assertEqual(result['retries'],1)

    def test_real_requests_share_budget_rate_limit_and_stop_policy(self):
        ids=['U01','U02','U04','U05']
        steps={cid:[{'delay':.2,'raw':{'model':default_binding()['model'],
            'choices':[{'message':{'role':'assistant','content':'验证结束。'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}}] for cid in ids}
        temp,result,out=run_real(ids,workers=4,max_inflight_requests=2,request_interval=.1,scripts_by_case=steps)
        self.addCleanup(temp.cleanup)
        self.assertTrue(result['complete'],result['halt'])
        self.assertLessEqual(result['budget']['max_observed_inflight'],2)
        rows=[json.loads(line) for line in (out/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
        granted=[r['time'] for r in rows if r['kind']=='request']
        self.assertEqual(len(granted),4)
        self.assertTrue(all(b-a>=.099 for a,b in zip(granted,granted[1:])),granted)
        temp,result,out=run_real(['U05'],workers=1,budget_limit='0',scripts_by_case={'U05':['不应执行。']})
        self.addCleanup(temp.cleanup)
        self.assertFalse(result['complete'])
        self.assertEqual(result['budget']['requests'],0)
        self.assertFalse((out/'U05/api-script-state.json').exists())
        temp,result,out=run_real(['U05','U04'],workers=1,case_timeout=3,
            scripts_by_case={'U05':[{'delay':8,'tool':'read_file','arguments':{'path':'cli.py'}}],'U04':['不应执行。']})
        self.addCleanup(temp.cleanup)
        self.assertFalse(result['complete'])
        self.assertEqual(result['budget']['requests'],1)
        self.assertEqual(len(result['budget']['unknown_requests']),1)
        self.assertEqual(result['cases'][1]['status'],'not_run')
        self.assertEqual(inspect_run(out)['status'],'needs_recovery')

    def test_freeze_and_provider_approval_do_not_create_client(self):
        ROOT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'plan.json'
            cfg={**default_binding(),'backend':'real','transport':'provider_api','validation':False,'case_ids':['U05']}
            sha=freeze_plan(cfg,path)
            self.assertEqual(sha,sha256(path.read_bytes()).hexdigest())
            frozen=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(frozen['effective_parameters']['max_tokens'],4096)
            self.assertEqual(frozen['effective_parameters']['sdk_max_retries'],0)
            self.assertIn(str((Path(frozen['suite'])/'cases/U05/input/cli.py').resolve()),frozen['binding_files'])
            self.assertIn(str((BASE/'work/formal-engineering.py').resolve()),frozen['binding_files'])
            self.assertIn(str(ENTRY.with_name('formal-current-mxc.py').resolve()),frozen['binding_files'])
            invalid={**frozen,'out':str(Path(temp)/'run'),'plan_file':str(path),'approved_plan_sha256':'0'*64}
            with self.assertRaises(PermissionError):run_batch(invalid,load_cases(invalid,['U05']))
            self.assertFalse(Path(invalid['out']).exists())

    def test_freeze_rejects_silently_ignored_model_parameters(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            for changes in ({'max_tokens':128},{'request_body':{'enable_thinking':True}}, {'currency':'USD'}):
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError,'effective'):
                    freeze_plan({'case_ids':['U05'],'transport':'provider_api','validation':False,**changes},Path(temp)/'plan.json')

    def test_manifest_drift_refuses_before_execution(self):
        config={**default_binding(),'backend':'real','transport':'scripted_api','validation':True,'workers':1,'runtime_entry_sha256':'0'*64}
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            config['out']=str(Path(temp)/'run')
            with self.assertRaisesRegex(ValueError,'fingerprint'):
                run_batch(config,load_cases(config,['U05']))
            self.assertFalse(Path(config['out']).exists())


if __name__=='__main__': unittest.main()
