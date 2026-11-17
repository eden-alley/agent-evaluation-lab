"""Daily evaluation entry: execute, hand back to the initiating Agent, submit."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys

from capability_review import Client, ReviewClientError
from formal20_archive import digest, read
from formal20_concurrent import run_batch
from formal20_pipeline import (_validate_destination, finalize_run, resume_delivery,
                               submit_analysis_task, validate_delivery_paths)
from formal20_runtime import (default_binding, freeze_plan, inspect_run, load_cases,
                              resume_run, validate_binding)
from formal20_worker import write_json
from formal20_start_guard import validate_run_id
from lab.comparisons.review_schemas import ReviewPreparation

ROOT=Path(__file__).resolve().parents[1]


def method_entry():
    catalog=read(ROOT/'skills/catalog.json')
    entry=next(e for e in catalog['skills'] if e['slug']=='agent-version-comparison-workflow')
    payload=read(ROOT/'skills'/entry['payload_file'])
    if digest({'content':payload['content']})!=entry['platform_content_hash']:
        raise ValueError('Skill package differs from catalog; rebuild the package first')
    return entry,payload


def sync_skill(api):
    """Publish the packaged version through normal APIs; never rewrite old content."""
    entry,payload=method_entry()
    matches=[s for s in api.request('GET','/skills')['items'] if s['name']==entry['catalog']['name']]
    if len(matches)>1:raise ValueError('Multiple matching Skill entries; choose the intended directory explicitly')
    skill=matches[0] if matches else api.request('POST','/skills',json=entry['catalog'])
    active=skill.get('active_version')
    if not active or active['content_hash']!=entry['platform_content_hash']:
        version=api.request('POST',f"/skills/{skill['id']}/versions",json=payload)
        skill=api.request('POST',f"/skills/{skill['id']}/versions/{version['id']}/publish")
        active=skill['active_version']
    if active['content_hash']!=entry['platform_content_hash']:raise ValueError('Published Skill differs from package')
    return {'skill_id':skill['id'],'version_id':active['id'],'content_hash':active['content_hash']}


def delivery_config(config):
    delivery=config.get('delivery')
    if not isinstance(delivery,dict):raise ValueError('Daily entry requires delivery configuration before execution')
    for key in config.keys() & delivery.keys():
        if key!='delivery' and config[key]!=delivery[key]:
            raise ValueError('执行与交付配置冲突：'+key)
    execution_keys={'model','suite','case_ids','source_harness','validation','transport','workers',
        'runtime_entry','runtime_entry_sha256','harness_version','binding_files','effective_parameters','output_policy',
        'scripts_by_case','max_requests','max_requests_per_case','budget_limit','max_retries',
        'max_inflight_requests','request_interval','baseline_only','plan_file','approved_plan_sha256','out'}
    if any(key in delivery and key not in config for key in execution_keys):
        raise ValueError('执行字段必须在顶层固定，不能只放在delivery中')
    cfg={**config,**delivery}
    required=('api_url','data_root','archive_root','run_id','project_id','project_name','name','version','workflow')
    missing=[k for k in required if not cfg.get(k)]
    if missing:raise ValueError('Missing delivery fields: '+', '.join(missing))
    if not config.get('baseline_only') and not cfg.get('baseline_run_id'):
        raise ValueError('Select baseline_run_id, or explicitly start --baseline-only')
    if config.get('baseline_only') and cfg.get('baseline_run_id'):
        raise ValueError('baseline-only cannot also request an A/B comparison')
    validate_run_id(cfg['run_id'])
    if str(cfg['version']).removeprefix('v')!=str(config.get('harness_version')).removeprefix('v'):
        raise ValueError('归档版本必须与实际执行Harness版本一致')
    return cfg


def validation_paths(config,out=None):
    cfg=delivery_config(config)
    if not cfg.get('validation'):return
    protected=(ROOT/'data').resolve()
    paths=[cfg.get(key) for key in ('data_root','archive_root','control_dir')]
    paths.extend((out,config.get('out')))
    if any(Path(path).resolve().is_relative_to(protected) for path in paths if path):
        raise ValueError('假模型验证的输出、归档和控制目录必须隔离，不能写日常data及其子目录')


@contextmanager
def platform(config,api=None):
    cfg=delivery_config(config)
    validation_paths(config)
    client=api if api is not None else Client(cfg['api_url'])
    try:
        _validate_destination(cfg,client)
        yield client
    finally:
        if api is None:client.close()


def preflight(config,api,out=None):
    cfg=delivery_config(config)
    validate_delivery_paths(cfg,out)
    preparation=ReviewPreparation.model_validate({'review_scope':cfg.get('review_scope','focused'),
        'explain_case_ids':cfg.get('explain_case_ids')})
    selected=preparation.explain_case_ids
    if selected and (len(selected)!=len(set(selected)) or not set(selected).issubset(config['case_ids'])):
        raise ValueError('讲解题必须唯一且属于本批case_ids')
    # Inspect the frozen entry as data. Importing it here would preload original
    # graders in the launcher before execution and weaken offline import guards.
    validate_binding(config)
    entry=Path(config['runtime_entry']).resolve()
    assignments={target.id:node.value for node in ast.parse(entry.read_text(encoding='utf-8')).body
        if isinstance(node,ast.Assign) for target in node.targets if isinstance(target,ast.Name)}
    actual_version=ast.literal_eval(assignments['HARNESS_VERSION'])
    source_expression=ast.parse("Path(__file__).resolve().parents[1] / 'source'",mode='eval').body
    if ast.dump(assignments['FROZEN_SOURCE'])!=ast.dump(source_expression):
        raise ValueError('冻结入口源码布局不同，需要先明确适配，不能猜测源码身份')
    if str(config['harness_version']).removeprefix('v')!=str(actual_version).removeprefix('v'):
        raise ValueError('声明版本与冻结执行入口的实际版本不一致')
    if Path(config['source_harness']).resolve()!=entry.parent.parent/'source':
        raise ValueError('声明源码与冻结执行入口实际加载的源码不一致')
    health=_validate_destination(cfg,api)
    if not health.get('capabilities',{}).get('comparison_statistics_snapshot'):
        raise ValueError('平台尚未加载固定统计与报告链路，请先更新并重启平台，再启动评测')
    api.request('GET','/projects/'+cfg['project_id'])
    ref=cfg['workflow']
    version=api.request('GET',f"/skills/{ref['skill_id']}/content",params={'version_id':ref['version_id']})['version']
    entry,_=method_entry()
    if version['content_hash']!=ref['content_hash'] or ref['content_hash']!=entry['platform_content_hash']:
        raise ValueError('Publish and pin the current packaged Skill before starting this run')
    if cfg.get('baseline_run_id'):
        baseline=api.request('GET','/evaluation-runs/'+cfg['baseline_run_id'])
        if baseline['project_id']!=cfg['project_id']:raise ValueError('Baseline belongs to another project')
        if not set(config['case_ids']).issubset(c['id'] for c in baseline['cases']):
            raise ValueError('Baseline does not contain all selected cases')
    for folder in (Path(cfg['archive_root'])/cfg['run_id'],Path(cfg['data_root'])/'evaluation-runs'/cfg['run_id']):
        if folder.exists():raise FileExistsError('run_id already exists; keep history and choose a new ID')


def save_run_context(run,config):
    path=Path(run)/'task-context.json'
    if path.exists() and read(path)!=config:raise ValueError('The initiating task configuration has changed')
    if not path.exists():write_json(path,config)


def claim_provider_plan(config,out):
    """Compatibility entry for the shared approval and run_id reservation."""
    from formal20_start_guard import claim_start
    delivery_config(config)
    return claim_start(config,out,provider=True)


def make_handoff(run,config,state):
    run=Path(run).resolve();cfg=delivery_config(config)
    control=Path(state.get('control_dir') or cfg.get('control_dir') or run.with_name(run.name+'-delivery')).resolve()
    control.mkdir(parents=True,exist_ok=True)
    review=Path(state.get('active_review_dir') or control).resolve()
    if not review.is_relative_to(control):raise ValueError('Active review is outside the initiating task')
    status=state['status'];packet=read(review/'packet.json',{})
    complete=status=='delivery_complete'
    if complete:
        receipt=read(review/'receipt.json',{})
        if not receipt.get('report_id') or receipt!=state.get('receipt'):
            raise ValueError('A matching report receipt is required for task completion')
        request=read(review/'request.json',{});report=read(review/'report.json',{})
        if (receipt.get('request_id')!=request.get('request_id') or
                receipt.get('report_id')!=report.get('id') or
                receipt.get('report_hash')!=report.get('report_hash') or
                report.get('request_id')!=request.get('request_id') or
                report.get('packet_hash')!=packet.get('packet_hash') or
                receipt.get('delivery_id')!=packet.get('delivery_id')):
            raise ValueError('The active packet, request, report and receipt must match')
    submit=[sys.executable,'-B',str(ROOT/'scripts/evaluation.py'),'submit','--run',str(run),'--analysis',str(review/'analysis.json')]
    result={**state,'status':status,'execution_complete':status not in ('execution_pending','needs_recovery'),
        'task_complete':complete or (bool(config.get('baseline_only')) and status=='baseline_required'),
        'report_complete':complete,'run_dir':str(run),'control_dir':str(control),'active_review_dir':str(review),
        'workflow':packet.get('workflow',cfg['workflow']),'read_first':str(review/'Skill正文.md'),
        'materials':str(review/'materials.json'),'metrics':str(review/'指标升降表.md'),
        'analysis':str(review/'analysis.json'),'continuation':str(control/'继续本次任务.md'),
        'submit_argv':submit if status=='analysis_pending' else None}
    if status=='analysis_pending':
        instruction=('发起这次评测的外部 Agent 继续同一次任务，当前还没有完成报告交付。\n\n'
            '1. 读取下面固定 Skill 正文、材料摘要和指标表。\n'
            '2. 从退步、异常和建议依据中选关键题，按回复区间讲清动作、反馈、转折与验收，并引用原件。\n'
            '3. 读取 review_policy；正式整批且超过3题才可附有据建议，可以零建议。\n'
            '4. 填写已有 analysis.json，调用下面 submit_argv；收到报告回执后再向用户报告完成。\n'
            '材料读取、统计和提交交给程序。不要只发材料让用户另找 Agent，不启动额外模型或重跑任务。\n\n')
    elif complete:instruction='报告已提交，回执已核对。本次任务的程序交付完成；语义质量仍以证据审阅为准。\n\n'
    elif status=='baseline_required':instruction='本次已保存为首批基线。没有A/B对照，不宣称指标升降或分析报告已完成。\n\n'
    else:instruction='执行尚未完整结束。保留原账本和现场，按恢复检查处理；不要重跑或宣称报告交付完成。\n\n'
    (control/'继续本次任务.md').write_text(instruction+json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_json(control/'task-handoff.json',result)
    return result


def start_evaluation(config,out,*,api=None,baseline_only=False,plan_path=None,approved_sha=None):
    config={**default_binding(),**config,'backend':'real'}
    provider=config.get('transport')=='provider_api'
    if provider:
        if not plan_path or not approved_sha:raise PermissionError('Provider start requires a frozen plan and this run approval hash')
        if baseline_only and not config.get('baseline_only'):raise PermissionError('baseline-only must be part of the approved plan')
        config.update(plan_file=str(Path(plan_path).resolve()),approved_plan_sha256=approved_sha)
        validate_binding(config)
    elif config.get('transport')!='scripted_api' or config.get('validation') is not True:
        raise PermissionError('Config starts are limited to explicitly labelled scripted API validation')
    if baseline_only:config['baseline_only']=True
    delivery_config(config)
    out=Path(out).resolve()
    validation_paths(config,out)
    if out.exists():raise FileExistsError('Output directory already exists')
    with platform(config,api) as client:
        preflight(config,client,out)
        if not plan_path:
            control=Path(config['delivery'].get('control_dir') or out.with_name(out.name+'-delivery'))
            control.mkdir(parents=True,exist_ok=True)
            path=control/'execution-plan.json'
            freeze_plan(config,path);config=read(path)
            config.update(plan_file=str(path.resolve()),approved_plan_sha256=None)
        config['out']=str(out)
        if provider:config['approval_record']=claim_provider_plan(config,out)
        else:
            from formal20_start_guard import claim_start
            config['execution_start_record']=claim_start(config,out)
        result=run_batch(config,load_cases(config,config['case_ids']))
        config=result['config'];save_run_context(out,config)
        state=finalize_run(delivery_config(config),out,client) if result['complete'] else {
            'status':'execution_pending','halt':result['halt']}
        return make_handoff(out,config,state)


def continue_evaluation(run,*,api=None):
    run=Path(run).resolve();config=read(run/'task-context.json') or read(run/'config.json')
    if not config:raise ValueError('No saved initiating task configuration')
    summary=read(run/'summary.json',{})
    if not summary.get('complete'):
        decision=inspect_run(run)
        if decision['status']!='checkpoint_paused':
            return make_handoff(run,config,{'status':'needs_recovery','reason':decision.get('reason')})
        summary=resume_run(config,run)
        if not summary['complete']:return make_handoff(run,config,{'status':'execution_pending','halt':summary['halt']})
    with platform(config,api) as client:
        cfg=delivery_config(config);control=Path(cfg.get('control_dir') or run.with_name(run.name+'-delivery'))
        state=resume_delivery(control,client) if (control/'delivery-context.json').exists() else finalize_run(cfg,run,client)
        return make_handoff(run,config,state)


def submit_evaluation(run,analysis,*,api=None):
    run=Path(run).resolve();config=read(run/'task-context.json') or read(run/'config.json')
    if not config or not read(run/'summary.json',{}).get('complete'):
        raise ValueError('The execution must finish before analysis submission')
    cfg=delivery_config(config);control=Path(cfg.get('control_dir') or run.with_name(run.name+'-delivery'))
    with platform(config,api) as client:
        return make_handoff(run,config,submit_analysis_task(control,analysis,client))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    freeze=sub.add_parser('freeze');freeze.add_argument('--config',type=Path,required=True);freeze.add_argument('--out',type=Path,required=True)
    sync=sub.add_parser('sync-skill');sync.add_argument('--api-url',required=True)
    start=sub.add_parser('start');source=start.add_mutually_exclusive_group(required=True)
    source.add_argument('--config',type=Path);source.add_argument('--plan',type=Path)
    start.add_argument('--out',type=Path,required=True);start.add_argument('--approved-plan-sha256');start.add_argument('--baseline-only',action='store_true')
    cont=sub.add_parser('continue');cont.add_argument('--run',type=Path,required=True)
    submit=sub.add_parser('submit');submit.add_argument('--run',type=Path,required=True);submit.add_argument('--analysis',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='freeze':result={'plan_sha256':freeze_plan(read(args.config),args.out),'plan':str(args.out)}
    elif args.command=='sync-skill':
        client=Client(args.api_url)
        try:result={'workflow':sync_skill(client)}
        finally:client.close()
    elif args.command=='start':result=start_evaluation(read(args.config or args.plan),args.out,baseline_only=args.baseline_only,
            plan_path=args.plan,approved_sha=args.approved_plan_sha256)
    elif args.command=='continue':result=continue_evaluation(args.run)
    else:result=submit_evaluation(args.run,args.analysis)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('status') in ('needs_recovery','execution_pending') else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,PermissionError,FileExistsError,ReviewClientError) as error:
        print(json.dumps({'status':'needs_attention','task_complete':False,'error':str(error)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
