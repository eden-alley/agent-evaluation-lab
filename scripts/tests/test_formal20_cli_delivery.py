"""CLI delivery routing: a paused execution is not an immutable final archive."""
import json
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from formal20_concurrent import main
from formal20_runtime import default_binding,freeze_plan

class CLIDeliveryTests(unittest.TestCase):
    def cli(self,resume,complete):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plan=root/'plan.json';run=root/'run'
            cfg={**default_binding(),'transport':'scripted_api','validation':True,'case_ids':['U05'],
                 'baseline_only':True,'delivery':{'api_url':'http://127.0.0.1:8116','run_id':'cli-validation',
                     'data_root':str(root/'platform'),'archive_root':str(root/'archives'),
                     'project_id':'cli-project','project_name':'cli project','name':'cli validation',
                     'version':default_binding()['harness_version'],'workflow':{'skill_id':'s','version_id':'v','content_hash':'h'}}}
            freeze_plan(cfg,plan);cfg=json.loads(plan.read_text(encoding='utf-8'))
            result={'mode':'integration_validation','complete':complete,'counts':{},
                    'halt':None if complete else 'checkpoint_paused','config':cfg}
            argv=['runner','resume','--plan',str(plan),'--run',str(run)] if resume else [
                'runner','execute','--plan',str(plan),'--out',str(run),'--transport','scripted_api','--validation']
            with patch.object(sys,'argv',argv),patch('formal20_runtime.resume_run',return_value=result),\
                 patch('formal20_runtime.load_cases',return_value=[]),patch('formal20_concurrent.run_batch',return_value=result),\
                 patch('evaluation.platform',return_value=nullcontext(MagicMock())),patch('evaluation.preflight'),\
                 patch('formal20_pipeline.finalize_run',return_value={'status':'analysis_pending'}) as finalize,\
                 patch('capability_review.Client',return_value=MagicMock()):
                status=main()
                self.assertEqual(status,0 if complete else 2)
                self.assertEqual(finalize.call_count,1 if complete else 0)
                if complete:self.assertEqual(Path(finalize.call_args.args[1]),run)

    def test_paused_execution_does_not_publish_final_archive(self):self.cli(False,False)
    def test_completed_resume_uses_same_delivery_chain(self):self.cli(True,True)
    def test_completed_execute_uses_delivery_chain(self):self.cli(False,True)

if __name__=='__main__':unittest.main()
