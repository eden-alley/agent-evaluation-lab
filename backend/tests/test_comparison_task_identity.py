"""Budget/description differences preserve task identity, substantive requirements do not."""
from copy import deepcopy
import json
import shutil

import pytest
from test_comparisons import comparison_env, CASE, create, case_materials, analysis_payload
from lab.comparisons import service


def actual_pair(env, *, change=None):
    _, folder, _ = env
    run = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    task = run['cases'][0]['task']
    task['controls'] = {'requests_per_case_cap': 30, 'allowed_changes': ['src.py', 'report.md'],
                        'controller': 'same-grader', 'attempts': 1}
    task['difficulty_basis'] = '原难度说明'
    task['checks'] = [{'id':'result','rule':'修复功能并保持原有测试'}]
    (folder / 'run.json').write_text(json.dumps(run,ensure_ascii=False),encoding='utf-8')
    dest = folder.parent / 'candidate'
    shutil.copytree(folder,dest)
    candidate = deepcopy(run);candidate['id'] = 'candidate'
    new = candidate['cases'][0]['task']
    new['controls']['requests_per_case_cap'] = 60
    new['difficulty_basis'] = '含义相同的新版难度说明'
    if change == 'prompt': new['turns'][0]['content'] = '另一个任务'
    if change == 'criterion': new['checks'][0]['rule'] = '只要生成文件就通过'
    if change == 'protection': new['controls']['allowed_changes'].append('protected.py')
    (dest / 'run.json').write_text(json.dumps(candidate,ensure_ascii=False),encoding='utf-8')
    return {'kind':'run','run_id':'candidate'}


def test_budget_and_difficulty_description_allow_reports_and_keep_original_controls(comparison_env):
    candidate = actual_pair(comparison_env)
    plan = create(comparison_env,candidate=candidate)
    assert plan['queue'][0]['task_state'] == 'same'
    context = case_materials(comparison_env,plan)
    assert context['baseline']['case']['task']['controls']['requests_per_case_cap'] == 30
    assert context['candidate']['case']['task']['controls']['requests_per_case_cap'] == 60
    response = comparison_env[0].post(f"/api/v1/comparisons/{plan['id']}/cases/{CASE}/analyses",
        json=analysis_payload(context))
    assert response.status_code == 201,response.text


@pytest.mark.parametrize('change',['prompt','criterion','protection'])
def test_changed_requirements_still_block_capability_claims(comparison_env,change):
    candidate = actual_pair(comparison_env,change=change)
    plan = create(comparison_env,candidate=candidate)
    assert plan['queue'][0]['task_state'] == 'changed_task'
    response = comparison_env[0].post(f"/api/v1/comparisons/{plan['id']}/cases/{CASE}/analyses",
        json=analysis_payload(case_materials(comparison_env,plan)))
    assert response.status_code == 422


def test_legacy_hashes_can_be_compared_without_rewriting_saved_snapshot():
    a = {'turns':[{'role':'user','content':'same task'}],
         'controls':{'requests_per_case_cap':30},'difficulty_basis':'old prose'}
    b = deepcopy(a);b['controls']['requests_per_case_cap'] = 60;b['difficulty_basis'] = 'new prose'
    snapshot = {'baseline':{'cases':{'x':{'case':{'task':a},'task_hash':'legacy-a'}}},
                'candidate':{'cases':{'x':{'case':{'task':b},'task_hash':'legacy-b'}}}}
    before = deepcopy(snapshot)
    assert service.task_state(snapshot,'x') == 'same'
    assert snapshot == before
