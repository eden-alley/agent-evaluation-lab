"""Configurable dispatcher with synthetic regression and frozen real execution paths."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
from hashlib import sha256
import json
import math
import multiprocessing as mp
from multiprocessing.connection import wait
import os
from pathlib import Path
import re
import subprocess
import time

from formal20_coordinator import Coordinator, CoordinatorError
from formal20_worker import OfflineBoundary, worker_main, write_json


def positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return value


def synthetic_cases(count=20):
    return [{'id':f'SIM-{i:02}','kind':'normal','delay':.03} for i in range(1,count+1)]


def terminate_tree(process):
    if not process.is_alive(): return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    if process.is_alive(): process.kill()
    process.join(2)


def run_batch(config, cases):
    """Run isolated cases through the shared process, accounting and summary path."""
    workers=positive(config.get('workers',2),'workers')
    cap=positive(config.get('max_inflight_requests',workers),'max_inflight_requests')
    interval=config.get('request_interval',0)
    timeout=config.get('timeout_after_ready',config.get('case_timeout',10))
    if isinstance(interval,bool) or not isinstance(interval,(int,float)) or not math.isfinite(interval) or interval<0:
        raise ValueError('request_interval must be nonnegative')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0:
        raise ValueError('case_timeout must be positive')
    cases=list(cases)
    backend=config.get('backend','synthetic')
    if backend not in ('synthetic','real'):raise ValueError('Unknown execution backend')
    pattern=r'SIM-[A-Za-z0-9-]+' if backend=='synthetic' else r'[A-Za-z0-9_-]+'
    if not cases or any(not re.fullmatch(pattern,c.get('id','')) for c in cases):
        raise ValueError('Invalid case IDs')
    if len({c['id'] for c in cases})!=len(cases): raise ValueError('Duplicate case ID')
    if backend=='real':
        from formal20_runtime import validate_binding
        validate_binding(config)
    if config.get('max_retries',0) not in (0,1):raise ValueError('max_retries must be 0 or 1')
    out=Path(config['out']).resolve()
    from formal20_start_guard import execution_lock
    with execution_lock(out):
        if config.get('_resume'):
            if not (out/'config.json').is_file():raise ValueError('No existing run configuration')
        elif out.exists():raise FileExistsError('Output directory already exists')
        if backend=='real':
            from formal20_start_guard import guard_batch_start
            config=guard_batch_start(config,out)
        if not config.get('_resume'):out.mkdir(parents=True,exist_ok=False)
        saved_config={'budget_limit':'10','max_requests':1200,'max_requests_per_case':60,
                      'prompt_price_per_million':'2','output_price_per_million':'8',
                      **{k:v for k,v in config.items() if k!='out'},'workers':workers,'max_inflight_requests':cap,
                      'request_interval':interval,'case_timeout_seconds':timeout,'out':str(out),'backend':backend}
        saved_config['case_ids']=[c['id'] for c in cases]
        write_json(out/'config.json',saved_config)
        with (OfflineBoundary() if backend=='synthetic' or config.get('validation') else nullcontext()):
            return _run(saved_config,cases,out,timeout)


def _run(config,cases,out,timeout):
    context=mp.get_context('spawn')
    coordinator=Coordinator(out,budget_limit=config.get('budget_limit','10'),
        max_requests=config.get('max_requests',1200),max_requests_per_case=config.get('max_requests_per_case',60),
        max_inflight_requests=config['max_inflight_requests'],min_request_interval=config['request_interval'],
        prompt_price_per_million=config.get('prompt_price_per_million','2'),
        output_price_per_million=config.get('output_price_per_million','8'),
        currency=config.get('currency','CNY' if config['backend']=='real' else 'SIM'),
        resume=config.get('_resume',False),binding={k:config.get(k) for k in ('runtime_entry_sha256','binding_files','transport','workers')})
    if config.get('_resume'):coordinator.resume_checkpoint_pause()
    begun=time.monotonic()
    states={c['id']:{'id':c['id'],'status':'not_run','resume_count':0,'processes':[]} for c in cases}
    if config.get('_resume'):
        for cid in states:
            path=out/cid/'worker-state.json'
            if path.exists():states[cid]=json.loads(path.read_text(encoding='utf-8'))
    definitions={c['id']:c for c in cases}
    active={}
    cursor=0
    first_wave=min(config['workers'],sum(s['status']!='completed' for s in states.values()))
    barrier_open=not config.get('start_barrier',True)
    first_ready=set()
    max_active=0
    request_owner={}
    if config.get('_resume') and (out/'requests.jsonl').exists():
        request_owner={row['request_id']:row['case'] for row in map(json.loads,(out/'requests.jsonl').read_text(encoding='utf-8').splitlines()) if row.get('kind')=='request'}
    errors=[]
    queue_wait=0.0
    response_wait=0.0
    received_responses=set()
    retry_counts={}

    def emit(kind, **data):
        with (out/'batch-events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'kind':kind,'time':time.monotonic(),**data})+'\n')

    def send(slot,message):
        try:
            slot['conn'].send(message); slot['waiting']=None
            return True
        except (EOFError,BrokenPipeError,OSError):
            slot['pipe_closed']=True
            return False

    def spawn(cid,resume=False):
        nonlocal max_active
        parent,child=context.Pipe()
        target=worker_main
        definition=definitions[cid]
        if config['backend']=='real':
            from formal20_runtime import real_worker_main
            target=real_worker_main;definition={**definition,'_runtime_config':config}
        process=context.Process(target=target,args=(definition,str(out),child,resume),name=cid)
        try: process.start()
        except BaseException:
            parent.close();child.close();raise
        child.close()
        state=states[cid]
        state.update(status='running',pid=process.pid)
        state['processes'].append(process.pid)
        active[cid]={'process':process,'conn':parent,'spawned_at':time.monotonic(),'ready':False,
                     'pipe_closed':False,'waiting':None,'resume':resume,'checkpoint':None,'result':None}
        max_active=max(max_active,len(active))
        emit('process_started',case=cid,pid=process.pid,resume=resume)

    def safe_stop(reason):
        try: coordinator.stop(reason)
        except (CoordinatorError,OSError) as error: errors.append('ledger:'+type(error).__name__)

    def safe_unknown(request_id,reason):
        try: coordinator.mark_unknown(request_id,reason)
        except (CoordinatorError,OSError) as error: errors.append('ledger:'+type(error).__name__)

    def halt_case(cid,reason):
        slot=active[cid]; slot.setdefault('infra_reason',reason)
        snapshot=coordinator.snapshot()
        for request_id,request in snapshot['inflight_requests'].items():
            if request.get('case_id',request.get('case'))==cid:
                safe_unknown(request_id,reason)
        safe_stop(reason)

    def checkpoint_valid(cid,slot):
        if config['backend']=='real':
            folder=out/cid
            try:
                snapshot=json.loads((folder/'checkpoint/default.json').read_text(encoding='utf-8'))
                if any(r['status']=='executing' for r in snapshot['run_state']['call_records'].values()): return False
                no_inflight=not any(r.get('case_id',r.get('case'))==cid for r in coordinator.snapshot()['inflight_requests'].values())
                if not no_inflight:return False
                if (folder/'interruption.json').exists():
                    record=json.loads((folder/'interruption.json').read_text(encoding='utf-8'))
                    receipt=folder/'workspace/receipt.txt'
                    return record.get('boundary')=='recorded' and receipt.is_file() and receipt.stat().st_mtime_ns==record['receipt_mtime_ns']
                return ((folder/'model-interruption.json').exists() and config.get('validation') and
                        snapshot['run_state']['request_inflight']=='model')
            except (OSError,ValueError,KeyError,TypeError):return False
        record=slot['checkpoint']
        receipt=out/cid/'workspace/receipt.txt'
        return (record and record.get('boundary')=='recorded' and receipt.is_file()
                and sha256(receipt.read_bytes()).hexdigest()==record.get('receipt_sha256')
                and not any(r.get('case_id',r.get('case'))==cid for r in coordinator.snapshot()['inflight_requests'].values()))

    def message(cid,data):
        nonlocal barrier_open,response_wait
        slot=active[cid]; state=states[cid]
        op=data.get('op');slot['waiting']=op
        slot['last_activity']=time.monotonic()
        if op=='ready':
            slot['ready']=True;slot['ready_at']=time.monotonic()
            first_ready.add(cid)
            if len(first_ready)>=first_wave: barrier_open=True
        elif op=='acquire':
            slot['queued_at']=time.monotonic()
            result=coordinator.acquire(cid,data['attempt_id'],data['reserve_cost'],data.get('prompt_metadata',{}))
            if result is not None: send(slot,result)
        elif op=='next_attempt':
            send(slot,{'status':'allocated','attempt_id':coordinator.next_attempt(cid)})
        elif op=='replay':
            body=coordinator.replay_response(cid,data['attempt_id'],data['payload_sha256'])
            send(slot,{'status':'replay','body':body})
        elif op=='consumed':
            if request_owner.get(data['request_id'])!=cid:raise ValueError('cross-case consumption')
            coordinator.register_consumed(data['request_id'])
            send(slot,{'status':'consumed'})
        elif op in ('settle','api_error'):
            request_id=data['request_id']
            if request_owner.get(request_id)!=cid: raise ValueError('cross-case request ID')
            slot.pop('request_deadline',None)
            if op=='settle':
                if request_id not in received_responses:
                    response_wait+=time.monotonic()-slot.get('request_granted_at',time.monotonic())
                    received_responses.add(request_id)
                reply=coordinator.settle(request_id,data.get('usage'),data.get('response_metadata',{}))
                if reply['status']=='unknown_usage': slot['infra_reason']='unknown_usage'
                send(slot,reply)
            else:
                reason=data.get('reason','api_exception')
                metadata=data.get('metadata')
                retryable=(metadata or {}).get('exception_type') in ('APIConnectionError','APITimeoutError','RateLimitError')
                logical=data.get('logical_request_id',cid)
                allow_retry=retryable and config.get('max_retries',0)==1 and retry_counts.get(logical,0)<1
                coordinator.mark_unknown(request_id,reason,metadata=metadata,stop=not allow_retry)
                if allow_retry:
                    retry_counts[logical]=retry_counts.get(logical,0)+1
                    send(slot,{'status':'retry_allowed'})
                else:
                    slot.setdefault('infra_reason',reason)
                    send(slot,{'status':'halted','reason':coordinator.snapshot()['halt']})
        elif op=='checkpoint':
            slot['checkpoint']=data
            if not checkpoint_valid(cid,slot): raise ValueError('invalid checkpoint boundary')
            send(slot,{'status':'checkpoint_recorded'})
            if data.get('halt_after_ack'): safe_stop('simulated_stop_at_checkpoint')
        elif op=='finished':
            slot['result']=data['result']
            send(slot,{'status':'saved'})
        elif op=='worker_error':
            halt_case(cid,'worker_error:'+data.get('reason','unknown'))
            send(slot,{'status':'halted'})
        elif op=='configuration_error':
            halt_case(cid,data.get('reason','configuration_drift'))
            send(slot,{'status':'halted','reason':coordinator.snapshot()['halt']})
        else: raise ValueError('unknown worker operation')

    def receive_available(cid):
        slot=active[cid]
        if slot['pipe_closed']: return False
        try:
            if not slot['conn'].poll(): return False
            message(cid,slot['conn'].recv())
            return True
        except (EOFError,BrokenPipeError,OSError):
            slot['pipe_closed']=True
            if (slot['result'] is None and not slot.get('case_limit')
                    and not coordinator.snapshot()['halt'] and not checkpoint_valid(cid,slot)):
                halt_case(cid,'worker_pipe_disconnected')
        except Exception as error:
            halt_case(cid,'protocol_error:'+type(error).__name__)
            send(slot,{'status':'halted','reason':str(error)})
        return False

    try:
        while cursor<len(cases) or active:
            while cursor<len(cases) and len(active)<config['workers'] and not coordinator.snapshot()['halt']:
                cid=cases[cursor]['id'];cursor+=1
                if states[cid]['status']=='completed':continue
                native_resume=config.get('_resume',False) and (out/cid/'checkpoint/default.json').exists()
                spawn(cid,resume=native_resume)
            connections={slot['conn']:cid for cid,slot in active.items() if not slot['pipe_closed']}
            if connections:
                for conn in wait(list(connections),timeout=.01):
                    cid=connections[conn]
                    receive_available(cid)
            elif active: time.sleep(.005)
            if barrier_open:
                for cid,slot in active.items():
                    if slot['waiting']=='ready':
                        if coordinator.snapshot()['halt']: send(slot,{'status':'halted','reason':'batch_stopped'})
                        else:
                            states[cid].setdefault('started_at',time.monotonic())
                            emit('case_resumed' if slot['resume'] else 'case_started',case=cid,pid=slot['process'].pid)
                            send(slot,{'status':'start'})
            try: permits=coordinator.dispatch()
            except CoordinatorError as error:
                errors.append('ledger:'+type(error).__name__)
                safe_stop('ledger_write_failure')
                for request_id in coordinator.snapshot()['inflight_requests']:
                    if request_id not in request_owner: safe_unknown(request_id,'permission_not_delivered')
                permits=[]
            for permit in permits:
                cid=permit['case_id']
                if permit['status']=='granted':
                    request_owner[permit['request_id']]=cid
                    if cid in active:
                        granted=time.monotonic()
                        queue_wait+=max(0,granted-active[cid].get('queued_at',granted))
                        active[cid]['request_granted_at']=granted
                        active[cid]['request_deadline']=granted+timeout
                elif cid in active: active[cid]['case_limit']=True
                if cid not in active or not send(active[cid],permit):
                    if permit['status']=='granted': safe_unknown(permit['request_id'],'permit_delivery_lost')
            if coordinator.snapshot()['halt']:
                for slot in active.values():
                    if slot['waiting'] in ('ready','acquire'):
                        send(slot,{'status':'halted','reason':coordinator.snapshot()['halt']})
            for cid,slot in list(active.items()):
                process=slot['process']; now=time.monotonic()
                if process.is_alive():
                    # Bootstrap/barrier waiting is not a hung task; reset on every IPC progress.
                    receive_available(cid)
                    now=time.monotonic()
                    if slot['waiting']=='acquire': expired=False
                    elif 'request_deadline' in slot: expired=now>slot['request_deadline']
                    else:
                        limit=timeout if slot['ready'] and states[cid].get('started_at') else max(timeout,15)
                        expired=now-slot.get('last_activity',slot['spawned_at'])>limit
                    # Windows readers do not share DELETE: never open a checkpoint
                    # while the worker is still atomically replacing it.
                    expected_close=slot['pipe_closed'] and (slot['result'] is not None or slot.get('case_limit')
                                    or checkpoint_valid(cid,slot)
                                    or (coordinator.snapshot()['halt'] and not slot.get('infra_reason')))
                    if slot['pipe_closed'] and expected_close:
                        process.join(.01)
                        if process.is_alive():
                            if now-slot.get('last_activity',now)<2: continue
                            halt_case(cid,'worker_shutdown_timeout');terminate_tree(process)
                    elif slot['pipe_closed']:
                        halt_case(cid,'worker_pipe_disconnected');terminate_tree(process)
                    elif expired:
                        halt_case(cid,'worker_timeout'); terminate_tree(process)
                    else: continue
                # Drain data queued immediately before process exit before classifying it.
                while receive_available(cid): pass
                process.join(1)
                exitcode=process.exitcode
                expected_exit=exitcode==86 or (exitcode==85 and config['backend']=='real' and config.get('validation'))
                if expected_exit and checkpoint_valid(cid,slot) and not config.get('auto_resume_validation',True):
                    safe_stop('checkpoint_paused')
                if expected_exit and checkpoint_valid(cid,slot) and not coordinator.snapshot()['halt'] and not states[cid]['resume_count']:
                    slot['conn'].close();process.close()
                    states[cid]['resume_count']+=1
                    spawn(cid,resume=True)
                    continue
                if expected_exit and checkpoint_valid(cid,slot) and coordinator.snapshot()['halt']:
                    status='stopped'
                elif exitcode!=0 or slot.get('infra_reason'):
                    halt_case(cid,slot.get('infra_reason',f'worker_exit:{exitcode}'))
                    status='infrastructure_error'
                elif slot['result'] is not None:
                    status='completed'
                elif slot.get('case_limit'): status='case_limit'
                elif coordinator.snapshot()['halt']: status='stopped'
                else:
                    halt_case(cid,'missing_case_result');status='infrastructure_error'
                state=states[cid]
                state.update(status=status,ended_at=time.monotonic(),exit_code=exitcode)
                state.setdefault('started_at',slot['spawned_at'])
                state['seconds']=state['ended_at']-state['started_at']
                if slot.get('infra_reason'): state['reason']=slot['infra_reason']
                if slot['result'] is not None: state['result']=slot['result']
                write_json(out/cid/('worker-state.json' if config['backend']=='real' else 'result.json'),state)
                emit('case_finished',case=cid,status=status)
                slot['conn'].close();process.close();del active[cid]
            if not active and coordinator.snapshot()['halt']: break
    except BaseException as error:
        errors.append(type(error).__name__)
        safe_stop('coordinator_error:'+type(error).__name__)
        raise
    finally:
        for cid,slot in list(active.items()):
            try: halt_case(cid,'coordinator_shutdown')
            finally:
                try: terminate_tree(slot['process'])
                finally:
                    slot['conn'].close();slot['process'].close()
    budget=coordinator.snapshot()
    counts=Counter(s['status'] for s in states.values())
    persisted=json.loads((out/'budget.json').read_text(encoding='utf-8'))==budget
    summary={'mode':'integration_validation' if config['backend']=='real' and config.get('validation') else 'offline_simulation' if config['backend']=='synthetic' else 'provider_execution',
             'config':config,'complete':counts['completed']==len(cases),
             'cases':list(states.values()),'counts':dict(counts),'halt':budget['halt'],'budget':budget,
             'retries':sum(retry_counts.values()),'budget_persisted':persisted,'real_model_calls':0 if config.get('validation',True) else budget['requests'],
             'original_evaluation_runs':0,'original_grader_runs':sum((out/c['id']/'grade/grade.json').exists() for c in cases),
             'metrics':{'max_active_cases':max_active,'max_inflight_requests':budget['max_observed_inflight'],
                        'batch_wall_seconds':time.monotonic()-begun,
                        'queue_wait_seconds_sum':queue_wait,'request_wait_seconds_sum':response_wait,
                        'case_runtime_seconds_sum':sum(s.get('seconds',0) for s in states.values())},
             'errors':errors}
    write_json(out/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    simulate=sub.add_parser('simulate')
    simulate.add_argument('--workers',type=int,default=2)
    simulate.add_argument('--max-inflight-requests',type=int)
    simulate.add_argument('--request-interval-ms',type=float,default=0)
    simulate.add_argument('--scenario',choices=('normal','api_error','crash','timeout','checkpoint','checkpoint-stop','unknown_usage','unexpected_checkpoint'),default='normal')
    simulate.add_argument('--out',type=Path,required=True)
    freeze=sub.add_parser('freeze');freeze.add_argument('--config',type=Path,required=True);freeze.add_argument('--out',type=Path,required=True)
    execute=sub.add_parser('execute');execute.add_argument('--plan',type=Path,required=True);execute.add_argument('--out',type=Path,required=True)
    execute.add_argument('--transport',choices=('scripted_api','provider_api'),required=True)
    execute.add_argument('--validation',action='store_true');execute.add_argument('--approved-plan-sha256')
    resume=sub.add_parser('resume');resume.add_argument('--run',type=Path,required=True);resume.add_argument('--plan',type=Path,required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    if args.command!='simulate':
        from formal20_runtime import freeze_plan,inspect_run,load_cases,resume_run
        if args.command=='freeze':
            print(json.dumps({'plan_sha256':freeze_plan(json.loads(args.config.read_text(encoding='utf-8')),args.out),'plan':str(args.out)}));return 0
        if args.command=='inspect':print(json.dumps(inspect_run(args.run),ensure_ascii=False));return 0
        plan=json.loads(args.plan.read_text(encoding='utf-8'))
        if args.command=='resume':
            result=resume_run(plan,args.run)
            config=result['config'];run_dir=args.run
        else:
            if plan.get('transport')!=args.transport or bool(plan.get('validation'))!=args.validation:raise ValueError('CLI transport/validation differs from frozen plan')
            config={**plan,'backend':'real','out':str(args.out),'plan_file':str(args.plan.resolve()),'approved_plan_sha256':args.approved_plan_sha256}
            from formal20_runtime import validate_binding
            from formal20_start_guard import claim_start
            validate_binding(config)
            if config.get('delivery'):
                from evaluation import platform,preflight,validation_paths
                validation_paths(config,args.out)
                with platform(config) as client:preflight(config,client,args.out)
            config['execution_start_record']=claim_start(config,args.out)
            result=run_batch(config,load_cases(config,config['case_ids']))
            run_dir=args.out
        # A paused execution must not publish an immutable, stale final run.
        # Successful resume enters the same delivery chain as initial completion.
        if result['complete'] and config.get('delivery'):
            from formal20_pipeline import finalize_run
            from capability_review import Client
            delivery=config['delivery']
            if not delivery.get('api_url'):raise ValueError('Explicit platform URL required for delivery')
            client=Client(delivery['api_url'])
            try:result['delivery']=finalize_run({**config,**delivery},run_dir,client)
            finally:client.close()
        print(json.dumps({'mode':result['mode'],'complete':result['complete'],'counts':result['counts'],'halt':result['halt'],
                          'delivery':result.get('delivery')},ensure_ascii=False))
        return 0 if result['complete'] else 2
    cases=synthetic_cases(20 if args.scenario=='normal' else max(args.workers+2,3))
    if args.scenario!='normal':
        cases[0]['kind']='checkpoint' if args.scenario=='checkpoint-stop' else args.scenario
        if args.scenario=='checkpoint-stop': cases[0].update(halt_at_checkpoint=True,pause_before_exit=.1)
    config={'workers':args.workers,'out':args.out,'request_interval':args.request_interval_ms/1000,
            'timeout_after_ready':.5 if args.scenario=='timeout' else 15,'start_barrier':True}
    if args.max_inflight_requests is not None: config['max_inflight_requests']=args.max_inflight_requests
    result=run_batch(config,cases)
    print(json.dumps({'out':str(args.out),'workers':args.workers,'complete':result['complete'],
                      'counts':result['counts'],'max_active_cases':result['metrics']['max_active_cases'],
                      'requests':result['budget']['requests'],'responses':result['budget']['response_count'],
                      'halt':result['halt']},ensure_ascii=False))
    return 0 if result['complete'] else 2


if __name__=='__main__': raise SystemExit(main())
