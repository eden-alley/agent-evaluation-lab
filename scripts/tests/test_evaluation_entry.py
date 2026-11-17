"""Daily-entry contracts against a real temporary platform; no model API."""
import importlib
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_formal20_pipeline as fixtures
from formal20_runtime import default_binding

class DailyEntryTests(unittest.TestCase):
    def setUp(self):
        self.entry=importlib.import_module('evaluation')
        self.env=fixtures.DeliveryTests(methodName='runTest');self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.original_skills=self.env.api.request('GET','/skills')['items']
        self.workflow=self.entry.sync_skill(self.env.api)
        delivery={k:v for k,v in self.env.config.items() if k not in ('suite','case_ids','source_harness','model','validation')}
        delivery.update(api_url='http://127.0.0.1:8118',workflow=self.workflow,review_scope='focused',explain_case_ids=['U05'],version=default_binding()['harness_version'])
        self.config={**default_binding(),'backend':'real','transport':'scripted_api','validation':True,
            'workers':1,'case_ids':['U05'],'delivery':delivery,'scripts_by_case':{'U05':['test']}}

    def test_missing_delivery_and_baseline_refuse_before_execution(self):
        for config in ({k:v for k,v in self.config.items() if k!='delivery'},
                       {**self.config,'delivery':{k:v for k,v in self.config['delivery'].items() if k!='baseline_run_id'}}):
            out=self.env.root/'must-not-run'
            with patch('evaluation.run_batch') as runner,self.assertRaises(ValueError):
                self.entry.start_evaluation(config,out,api=self.env.api)
            runner.assert_not_called();self.assertFalse(out.exists())

    def test_delivery_cannot_relabel_execution(self):
        for field,value in (('model','another-model'),('validation',False),('case_ids',['U04'])):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'冲突'):
                self.entry.delivery_config({**self.config,'delivery':{**self.config['delivery'],field:value}})

    def test_unapproved_provider_config_refuses_without_client(self):
        config={**self.config,'transport':'provider_api','validation':False}
        with patch('evaluation.Client') as client,self.assertRaises(PermissionError):
            self.entry.start_evaluation(config,self.env.root/'not-approved')
        client.assert_not_called()

    def test_skill_sync_is_idempotent_and_keeps_old_versions(self):
        before=self.env.api.request('GET','/skills/'+self.workflow['skill_id'])
        again=self.entry.sync_skill(self.env.api)
        after=self.env.api.request('GET','/skills/'+self.workflow['skill_id'])
        self.assertEqual(again,self.workflow)
        self.assertEqual(before['versions'],after['versions'])
        items=self.env.api.request('GET','/skills')['items']
        self.assertEqual(len(items),len(self.original_skills)+1)
        self.assertTrue({s['id'] for s in self.original_skills}.issubset(s['id'] for s in items))

    def test_wrong_published_skill_refuses_before_execution(self):
        config={**self.config,'delivery':{**self.config['delivery'],'workflow':{
            **self.workflow,'content_hash':'0'*64}}}
        with patch('evaluation.run_batch') as runner,self.assertRaises(ValueError):
            self.entry.start_evaluation(config,self.env.root/'wrong-method',api=self.env.api)
        runner.assert_not_called()

    def test_old_platform_without_saved_statistics_refuses_before_execution(self):
        original=self.env.api.request
        def old(method,path,**kwargs):
            value=original(method,path,**kwargs)
            if path=='/health':value['capabilities'].pop('comparison_statistics_snapshot',None)
            return value
        with patch.object(self.env.api,'request',old),self.assertRaisesRegex(ValueError,'统计'):
            self.entry.preflight(self.config,self.env.api)

    def test_fake_validation_cannot_write_daily_data_directory(self):
        config={**self.config,'delivery':{**self.config['delivery'],'data_root':str(self.entry.ROOT/'data')}}
        with self.assertRaisesRegex(ValueError,'日常'):
            with self.entry.platform(config,self.env.api):pass

    def test_fake_archive_control_and_output_cannot_enter_daily_data(self):
        for field in ('archive_root','control_dir','data_root'):
            with self.subTest(field=field):
                cfg={**self.config,'delivery':{**self.config['delivery'],field:str(self.entry.ROOT/'data/evaluation-runs/new-fake')}}
                with self.assertRaisesRegex(ValueError,'日常'):
                    with self.entry.platform(cfg,self.env.api):pass
        with patch('evaluation.run_batch') as runner,self.assertRaisesRegex(ValueError,'日常'):
            self.entry.start_evaluation(self.config,self.entry.ROOT/'data/new-fake',api=self.env.api)
        runner.assert_not_called()

    def test_bad_scope_and_explanation_selection_refuse_before_execution(self):
        for changes in ({'review_scope':'formal'},{'explain_case_ids':['O01']},{'explain_case_ids':['U05','U05']}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.entry.preflight({**self.config,'delivery':{**self.config['delivery'],**changes}},self.env.api)

    def test_preflight_does_not_load_original_grader_modules(self):
        before=set(sys.modules)
        self.entry.preflight(self.config,self.env.api)
        added=set(sys.modules)-before
        self.assertFalse([name for name in added if name.startswith(('grade-','formal-'))],added)

    def test_archive_version_must_match_actual_harness(self):
        cfg={**self.config,'delivery':{**self.config['delivery'],'version':'pretend-new-version'}}
        with self.assertRaisesRegex(ValueError,'版本'):self.entry.delivery_config(cfg)

    @unittest.skipUnless(os.name=='nt','Windows directory naming rules')
    def test_windows_alias_and_reserved_run_names_refuse_before_client(self):
        for name in ('Daily-Run.','NUL','con.json','COM1'):
            with self.subTest(name=name):
                cfg={**self.config,'delivery':{**self.config['delivery'],'run_id':name}}
                with patch('evaluation.Client') as client,self.assertRaises(ValueError):
                    self.entry.start_evaluation(cfg,self.env.root/('invalid-'+name))
                client.assert_not_called()

    def test_control_overlap_refuses_before_dispatch_or_output_creation(self):
        locations=(Path(self.config['delivery']['archive_root'])/'control',
                   Path(self.config['delivery']['data_root'])/'evaluation-runs/control',
                   Path(self.config['delivery']['data_root'])/'execution-approvals/control',None)
        for index,control in enumerate(locations):
            out=self.env.root/('never-dispatched-'+str(index))
            control=control or out/'control'
            with self.subTest(control=control):
                cfg={**self.config,'delivery':{**self.config['delivery'],'control_dir':str(control)}}
                with patch('evaluation.run_batch') as runner,self.assertRaisesRegex(ValueError,'outside'):
                    self.entry.start_evaluation(cfg,out,api=self.env.api)
                runner.assert_not_called()
                self.assertFalse(out.exists())
                self.assertFalse(control.exists())

    def test_output_cannot_overlap_start_reservation_storage(self):
        out=Path(self.config['delivery']['data_root'])/'execution-approvals'
        with patch('evaluation.run_batch') as runner,self.assertRaisesRegex(ValueError,'outside'):
            self.entry.start_evaluation(self.config,out,api=self.env.api)
        runner.assert_not_called()
        self.assertFalse(out.exists())

    def test_preflight_requires_server_storage_identity(self):
        original=self.env.api.request
        def missing(method,path,**kwargs):
            value=original(method,path,**kwargs)
            if path=='/health':value.pop('storage',None)
            return value
        with patch.object(self.env.api,'request',missing),self.assertRaisesRegex(ValueError,'storage'):
            self.entry.preflight(self.config,self.env.api)

    def test_real_http_storage_mismatch_refuses_before_execution(self):
        import socket
        import threading
        import time
        import uvicorn
        listener=socket.socket()
        listener.bind(('127.0.0.1',0));listener.listen(16)
        server=uvicorn.Server(uvicorn.Config(self.env.client.app,log_level='error',access_log=False))
        worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
        worker.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.02)
            self.assertTrue(server.started)
            port=listener.getsockname()[1]
            client=self.entry.Client(f'http://127.0.0.1:{port}')
            try:
                self.entry.preflight(self.config,client)
                wrong=self.env.root/'wrong-unstarted-store'
                cfg={**self.config,'delivery':{**self.config['delivery'],'data_root':str(wrong)}}
                out=self.env.root/'must-not-execute-http'
                with patch('evaluation.run_batch') as runner,self.assertRaisesRegex(ValueError,'storage'):
                    self.entry.start_evaluation(cfg,out,api=client)
                runner.assert_not_called()
                self.assertFalse(wrong.exists())
                self.assertFalse(out.exists())
            finally:client.close()
        finally:
            server.should_exit=True;worker.join(5);listener.close()

    def test_approved_plan_cannot_be_spent_in_a_second_output_directory(self):
        plan=self.env.root/'approved.json';plan.write_text('{}',encoding='utf-8')
        cfg={**self.config,'plan_file':str(plan),'approved_plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()}
        first=self.entry.claim_provider_plan(cfg,self.env.root/'first')
        original=Path(first).read_bytes()
        with self.assertRaises(PermissionError):self.entry.claim_provider_plan(cfg,self.env.root/'second')
        self.assertEqual(Path(first).read_bytes(),original)

    def test_handoff_requires_same_task_analysis_and_receipt(self):
        cfg={**self.config,'out':str(self.env.run)}
        state=self.entry.finalize_run({**cfg,**cfg['delivery']},self.env.run,self.env.api)
        handoff=self.entry.make_handoff(self.env.run,cfg,state)
        self.assertFalse(handoff['task_complete'])
        self.assertEqual(handoff['status'],'analysis_pending')
        self.assertEqual(handoff['workflow'],self.workflow)
        self.assertTrue(Path(handoff['read_first']).is_file())
        self.assertTrue(Path(handoff['materials']).is_file())
        self.assertIn('submit',handoff['submit_argv'])
        self.assertIn('同一次任务',Path(handoff['continuation']).read_text(encoding='utf-8'))
        with patch('evaluation.run_batch') as runner,patch('evaluation.resume_run') as resume:
            self.entry.save_run_context(self.env.run,cfg)
            fixtures.save(self.env.run/'summary.json',{'complete':True})
            resumed=self.entry.continue_evaluation(self.env.run,api=self.env.api)
        self.assertEqual(resumed['status'],'analysis_pending')
        runner.assert_not_called();resume.assert_not_called()

    def test_empty_analysis_is_rejected_by_real_platform(self):
        cfg={**self.config,'out':str(self.env.run)}
        state=self.entry.finalize_run({**cfg,**cfg['delivery']},self.env.run,self.env.api)
        self.entry.save_run_context(self.env.run,cfg)
        control=Path(state['control_dir'])
        fixtures.save(self.env.run/'summary.json',{'complete':True})
        fixtures.save(control/'analysis.json',{'summary':'Required U05 explanation is deliberately missing.','case_explanations':[]})
        with self.assertRaises(fixtures.ReviewClientError):
            self.entry.submit_evaluation(self.env.run,control/'analysis.json',api=self.env.api)
        self.assertFalse((control/'receipt.json').exists())

if __name__=='__main__':unittest.main()
