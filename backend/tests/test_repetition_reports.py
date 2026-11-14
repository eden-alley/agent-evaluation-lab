"""Real HTTP round trip pins process evidence and keeps old reports immutable."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from lab.comparisons import repetition
from test_comparisons import comparison_env, create, CASE
from test_repetition import sample
from test_skill_delivery import complete_document, prepare_delivery
from lab.comparisons.review import submission


def test_process_snapshot_submission_and_original_drift(comparison_env):
    client, folder, _ = comparison_env
    run=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    events,requests=sample()
    for row in requests: row['case']=CASE
    for name in ('baseline','candidate'):
        target=folder.parent/name;target.mkdir(exist_ok=True)
        records=[]
        for path,content in [('events.jsonl',events),('raw/model-requests.jsonl',requests)]:
            raw=('\n'.join(json.dumps(e) for e in content)+'\n').encode()
            file=target/path;file.parent.mkdir(exist_ok=True);file.write_bytes(raw)
            records.append({'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        value=deepcopy(run);value['id']=name;value['cases'][0]['files']=records
        (target/'run.json').write_text(json.dumps(value),encoding='utf-8')
        (target/'manifest.json').write_text(json.dumps({'files':records}),encoding='utf-8')
    plan=create(comparison_env,candidate={'kind':'run','run_id':'candidate'},analyst={'kind':'manual','name':'offline HTTP fixture'})
    packet=prepare_delivery(client,plan['id'])
    payload=submission(packet,complete_document(),'offline_program')
    base=f"/api/v1/comparisons/{plan['id']}"
    response=client.post(base+'/review',json=payload)
    assert response.status_code==201,response.text
    report=response.json();metric=report['metric_report']['repetition']
    assert (metric['before'],metric['after'],metric['direction'])==(1,1,'unchanged')
    refs=metric['cases'][0]['candidate']['items'][0]['evidence']
    assert any(e['path']=='raw/model-requests.jsonl' and 'same result' in e['excerpt'] for e in refs)
    assert any(o['id']=='useless_exact_repetition' for o in report['case_analyses'][0]['content']['observations'])
    original=report['report_hash']
    (folder.parent/'candidate/raw/model-requests.jsonl').write_text('changed',encoding='utf-8')
    assert client.post(base+'/verify').json()['source_state']=='changed'
    saved=client.get(base+'/reports/'+report['id']).json()
    assert saved['report_hash']==original and saved['metric_report']['repetition']==metric


def test_incomplete_or_other_rule_version_never_looks_like_zero_improvement():
    events,rows=sample();a=repetition.analyze(events,repetition.request_index(rows)['U05'])
    case={'task':{'turns':['same']}}
    snap={'case_ids':['U05'],'is_simulation':False,'baseline':{'cases':{'U05':{'case':case,'repetition':a,'task_hash':'same'}}},'candidate':{'cases':{'U05':{'case':case,'repetition':deepcopy(a),'task_hash':'same'}}}}
    snap['candidate']['cases']['U05']['repetition']['insufficient']=1
    assert repetition.aggregate(snap)['direction']=='insufficient'
    snap['candidate']['cases']['U05']['repetition']=dict(a,version='different-rules')
    assert repetition.aggregate(snap)['before'] is None


def test_net_equal_counts_still_report_offsetting_improvements_and_regressions():
    events,rows=sample();a=repetition.analyze(events,repetition.request_index(rows)['U05'])
    def entry(n):return {'case':{'task':{'turns':['same']}},'task_hash':'same','repetition':dict(a,useless=n)}
    snap={'case_ids':['one','two'],'is_simulation':False,'baseline':{'cases':{'one':entry(1),'two':entry(0)}},'candidate':{'cases':{'one':entry(0),'two':entry(1)}}}
    result=repetition.aggregate(snap)
    assert result['direction']=='mixed'
    assert result['improved_cases']==['one'] and result['regressed_cases']==['two']
