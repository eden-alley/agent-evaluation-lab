"""Production single-case path: frozen Agent/tools/scorer, injected SDK transport."""
from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from hashlib import sha256
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

from formal20_worker import RPC, Stopped, write_json, _credential_name

BASE=Path(r'C:\Users\叶宸玮\Documents\Codex\2026-11-06\new-chat-5')
ENTRY=BASE/'outputs/harness-v0.40-formal20-20261115/work/run-formal-current.py'
ENTRY_SHA='d4a353b49ecb3da046b58e761eef0005edab5da1323e39367dcdaafd3b8b8e8e'
_VALIDATION_ACTIVE=False
_PORTS=set()
_HOOK_INSTALLED=False


def digest(path): return sha256(Path(path).read_bytes()).hexdigest()
def payload_digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def default_binding():
    return {'runtime_entry':str(ENTRY),'runtime_entry_sha256':ENTRY_SHA,
            'suite':str(BASE/'outputs/harness-formal-20-v0.2'),'model':'deepseek-v4.1-flash-1017',
            'harness_version':'v0.40','source_harness':str(ENTRY.parent.parent/'source')}


_EFFECTIVE_KEYS=('connection','provider','model','base_url','api_key_env','model_version','thinking',
    'max_tokens','timeout','sdk_max_retries','adapter_body','request_body','currency',
    'prompt_price_per_million','output_price_per_million','max_steps_per_turn','attempts_per_case','paid_judge')


def output_policy(config):
    if 'output_policy' not in config:return None
    policy=config['output_policy']
    required={'max_tokens','timeout','output_truncation_recovery'}
    if not isinstance(policy,dict) or not required<=set(policy) or set(policy)-required-{'recovery_max_output_tokens'}:
        raise ValueError('output_policy must explicitly fix capacity, timeout and recovery')
    if type(policy['max_tokens']) is not int or policy['max_tokens']<=0:
        raise ValueError('output_policy max_tokens must be positive')
    if type(policy['timeout']) not in (int,float) or not math.isfinite(policy['timeout']) or policy['timeout']<=0:
        raise ValueError('output_policy timeout must be positive and finite')
    if type(policy['output_truncation_recovery']) is not int or policy['output_truncation_recovery'] not in (0,1):
        raise ValueError('output_policy recovery must be 0 or 1')
    recovery=policy.get('recovery_max_output_tokens')
    if recovery is not None and (type(recovery) is not int or recovery<=0):
        raise ValueError('output_policy recovery capacity must be positive')
    outer=config.get('timeout_after_ready',config.get('case_timeout'))
    if outer is not None and (type(outer) not in (int,float) or not math.isfinite(outer) or outer<=policy['timeout']):
        raise ValueError('Outer case timeout must exceed the model request timeout')
    return policy


def output_recovery_options(runner):
    return {key:runner.PARAMS[key] for key in ('output_truncation_recovery','recovery_max_output_tokens')
            if key in runner.PARAMS}


def effective_parameters(config):
    baseline=Path(config['suite'])/'execution-plan-bailian.json'
    params=json.loads(baseline.read_text(encoding='utf-8'))['parameters']
    params={**params,'max_steps_per_turn':60}
    effective={key:params[key] for key in _EFFECTIVE_KEYS}
    effective.update(output_policy(config) or {})
    for key,value in effective.items():
        if key in config and config[key]!=value:raise ValueError('Frozen effective parameter differs: '+key)
    if config.get('effective_parameters',effective)!=effective:raise ValueError('Frozen effective parameter snapshot differs')
    return effective


def execution_files(config):
    """Hash the exact original materials, graders, native boundary and dependencies."""
    suite=Path(config['suite']);entry=Path(config['runtime_entry']);source=Path(config['source_harness'])
    baseline_path=suite/'execution-plan-bailian.json'
    baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
    paths={entry,suite/'cases.json',baseline_path,Path(sys.executable).resolve(),
        *source.rglob('*.py'),*entry.parent.glob('*.py'),
        *(p for p in (suite/'cases').rglob('*') if p.is_file() and '__pycache__' not in p.parts),
        *(BASE/'work'/name for name in baseline['scripts']),
        *(Path(p) for p in baseline.get('dependencies',{})),
        *(Path(__file__).with_name(name) for name in ('formal20_runtime.py','formal20_concurrent.py','formal20_coordinator.py','formal20_worker.py','evaluation.py','formal20_start_guard.py') if Path(__file__).with_name(name).is_file())}
    # Legacy grading modules import shared helpers beyond the plan's top-level scripts.
    paths.update((BASE/'work').glob('*.py'))
    return {str(p.resolve()):digest(p) for p in sorted(paths)}


def validate_binding(config):
    entry=Path(config['runtime_entry']).resolve()
    if digest(entry)!=config['runtime_entry_sha256']: raise ValueError('runtime entry fingerprint changed')
    if not Path(config['suite']).resolve().is_relative_to(BASE): raise ValueError('Unexpected frozen suite')
    if config.get('transport') not in ('scripted_api','provider_api'): raise ValueError('Unknown transport')
    if config.get('transport')=='provider_api':
        if config.get('validation') or not config.get('approved_plan_sha256'):
            raise PermissionError('Provider execution requires a new approved plan')
        plan_file=Path(config.get('plan_file',''))
        if not plan_file.is_file() or digest(plan_file)!=config['approved_plan_sha256']:
            raise PermissionError('Approved execution plan fingerprint differs')
        frozen=json.loads(plan_file.read_text(encoding='utf-8'))
        if any(config.get(k)!=v for k,v in frozen.items()):raise PermissionError('Frozen plan parameters changed')
        if not config.get('binding_files') or not config.get('effective_parameters'):
            raise PermissionError('Provider execution requires complete frozen execution bindings')
        if execution_files(config)!=config['binding_files']:raise ValueError('Bound execution file set changed')
    elif not config.get('validation'): raise ValueError('Scripted API runs must be validation-labelled')
    effective_parameters(config)
    for path,value in config.get('binding_files',{}).items():
        if digest(path)!=value:raise ValueError('Bound dependency fingerprint changed: '+str(path))


def load_cases(config,ids):
    catalog=json.loads((Path(config['suite'])/'cases.json').read_text(encoding='utf-8'))
    mapping={c['id']:c for c in catalog}
    if len(ids)!=len(set(ids)) or any(cid not in mapping for cid in ids): raise ValueError('Unknown/duplicate task')
    return [mapping[cid] for cid in ids]


def _audit(event,args):
    if not _VALIDATION_ACTIVE: return
    if event=='import' and (args[0].split('.')[0] in ('openai','anthropic') or args[0]=='winreg'):
        raise PermissionError('Provider SDK/credential access is forbidden in validation')
    if event in ('socket.connect','socket.bind'):
        address=args[1]
        if isinstance(address,tuple):
            host,port=address[:2]
            if host not in ('127.0.0.1','::1','localhost') or (event=='socket.connect' and port not in _PORTS):
                raise PermissionError('Only the bound validation service is accessible')
    if event=='socket.getaddrinfo' and args[0] not in ('127.0.0.1','::1','localhost',None):
        raise PermissionError('External name lookup forbidden')


class ValidationBoundary(AbstractContextManager):
    def __enter__(self):
        global _VALIDATION_ACTIVE,_HOOK_INSTALLED
        for name in list(os.environ):
            if _credential_name(name): del os.environ[name]
        if not _HOOK_INSTALLED: sys.addaudithook(_audit);_HOOK_INSTALLED=True
        _VALIDATION_ACTIVE=True
        return self
    def __exit__(self,*args):
        global _VALIDATION_ACTIVE
        _VALIDATION_ACTIVE=False


def load_runtime(config):
    validate_binding(config)
    entry=Path(config['runtime_entry'])
    spec=importlib.util.spec_from_file_location('_bound_formal20_'+uuid4().hex,entry)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.select_connection('bailian')
    module.PARAMS.update(output_policy(config) or {})
    if config.get('validation'):
        def forbidden(): raise PermissionError('paid_client forbidden in validation')
        module.paid_client=forbidden
    if module.PARAMS['model']!=config['model']: raise ValueError('Frozen model differs')
    expected=effective_parameters(config)
    if any(module.PARAMS[k]!=value for k,value in expected.items()):
        raise ValueError('Loaded effective parameters differ')
    return module


class ScriptedAPIError(RuntimeError):
    def __init__(self,data):
        super().__init__(data.get('type','scripted_error'))
        self.error_type=data.get('type','APIConnectionError')
        self.status_code=data.get('status_code')
        self.request_id=data.get('provider_request_id')
        self.retry_after=data.get('retry_after')


class ScriptedAPI:
    """Only the SDK response boundary is fake; it never touches workspace files."""
    def __init__(self,steps,out,model):
        self.steps=steps;self.path=Path(out)/'api-script-state.json';self.model=model
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**payload):
        index=json.loads(self.path.read_text())['cursor'] if self.path.exists() else 0
        if index>=len(self.steps): raise ScriptedAPIError({'type':'ScriptedResponsesExhausted'})
        step=self.steps[index];write_json(self.path,{'cursor':index+1})
        if isinstance(step,dict) and step.get('delay'): time.sleep(step['delay'])
        if isinstance(step,dict) and 'error' in step: raise ScriptedAPIError(step['error'])
        if isinstance(step,dict) and 'raw' in step: raw=step['raw']
        else:
            message={'role':'assistant'}
            if isinstance(step,str): message['content']=step
            else:
                calls=step.get('tools',[step])
                encoded=json.dumps(payload.get('messages',[]),ensure_ascii=False)
                url=re.search(r'http://127\.0\.0\.1:\d+',encoded)
                message['tool_calls']=[]
                for i,c in enumerate(calls):
                    arguments=json.dumps(c.get('arguments',{}),ensure_ascii=False)
                    if '$SERVICE_URL' in arguments:
                        if not url:raise ValueError('No actual task service URL in model messages')
                        arguments=arguments.replace('$SERVICE_URL',url.group())
                    message['tool_calls'].append({'id':'scripted_'+str(index)+'_'+str(i),'type':'function',
                        'function':{'name':c['tool'],'arguments':arguments}})
            raw={'model':self.model,'choices':[{'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                 'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}
        return SimpleNamespace(model_dump=lambda **_: raw)


class RequestGuard:
    def __init__(self,runner,client,rpc,case_id,out,config):
        self.runner,self.client,self.rpc,self.cid,self.out,self.config=runner,client,rpc,case_id,Path(out),config
        self.path=self.out/'response-state.json';self.pending=json.loads(self.path.read_text()) if self.path.exists() else None
        self.runtime=None;self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def halt(self,reason):
        self.rpc.call({'op':'configuration_error','reason':reason})
        raise self.runner.RunLimit(reason)
    def checkpoint_saved(self):
        state=self.runtime.run_state
        summary_saved=(self.pending and self.pending.get('request_kind')=='summary' and
                       state.next_action=='request')
        if self.pending and not self.pending.get('consumed') and state.request_inflight is None and (state.response or summary_saved):
            self.rpc.call({'op':'consumed','request_id':self.pending['request_id']})
            self.pending['consumed']=True;write_json(self.path,self.pending)
    def validate_raw(self,raw):
        if raw.get('model')!=self.runner.PARAMS['model']:self.halt('response_model_mismatch')
        details=(raw.get('usage',{}).get('completion_tokens_details') or {})
        choices=raw.get('choices') or []
        if details.get('reasoning_tokens') or any(c.get('message',{}).get('reasoning_content') for c in choices if isinstance(c,dict)):
            self.halt('thinking_mode_mismatch')
    def create(self,**payload):
        params=self.runner.PARAMS
        if payload.get('model')!=params['model'] or payload.get('extra_body',{})!=params['adapter_body']:
            self.halt('model_configuration_drift')
        payload['extra_body']=params['request_body'].copy()
        if hasattr(self.runner,'request_output_cap'):
            try:cap=self.runner.request_output_cap(params,payload,self.runtime.run_state)
            except ValueError:self.halt('output_capacity_drift')
        else:
            if params.get('recovery_max_output_tokens') is not None:self.halt('unsupported_recovery_capacity')
            cap=params['max_tokens'];payload['max_tokens']=cap
        fingerprint=payload_digest(payload)
        pending=self.pending
        if pending and not pending.get('consumed'):
            if pending['payload_sha256']!=fingerprint: self.halt('needs_recovery:pending_payload_changed')
            reply=self.rpc.call({'op':'replay','attempt_id':pending['attempt_id'],'payload_sha256':fingerprint})
            if reply.get('body') is not None:
                raw=reply['body']
                self.validate_raw(raw)
                return SimpleNamespace(model_dump=lambda **_:raw)
        else:
            attempt=self.rpc.call({'op':'next_attempt'})['attempt_id']
            pending={'attempt_id':str(attempt),'payload_sha256':fingerprint,'consumed':False,
                     'request_kind':self.runtime.run_state.request_inflight,
                     'logical_request_id':f'{self.cid}:{self.runtime.run_state.run_id}:{self.runtime.run_state.steps_used}'}
        reserve=self.runner.cost(len(json.dumps(payload,ensure_ascii=False).encode())+16384,cap)
        permit=self.rpc.call({'op':'acquire','attempt_id':pending['attempt_id'],'reserve_cost':str(reserve),
                             'prompt_metadata':{'payload':payload,'payload_sha256':fingerprint,'logical_request_id':pending['logical_request_id']}})
        pending['request_id']=permit['request_id'];self.pending=pending;write_json(self.path,pending)
        try: response=self.client.chat.completions.create(**payload)
        except Exception as error:
            metadata={k:v for k,v in {'exception_type':getattr(error,'error_type',type(error).__name__),
                'status_code':getattr(error,'status_code',None),'provider_request_id':getattr(error,'request_id',None),
                'retry_after':getattr(error,'retry_after',None)}.items() if v is not None}
            reply=self.rpc.call({'op':'api_error','request_id':permit['request_id'],'reason':'api_exception:'+metadata['exception_type'],
                                 'logical_request_id':pending['logical_request_id'],'metadata':metadata})
            if reply.get('status')=='retry_allowed':
                self.pending=None
                write_json(self.path,{'consumed':True,'request_id':permit['request_id'],'attempt_id':pending['attempt_id'],'payload_sha256':fingerprint})
                return self.create(**{**payload,'extra_body':params['adapter_body']})
            raise self.runner.RunLimit(metadata['exception_type'])
        raw=response.model_dump(mode='json',exclude_none=True,warnings=False)
        reply=self.rpc.call({'op':'settle','request_id':permit['request_id'],'usage':raw.get('usage'),'response_metadata':{'body':raw}})
        if reply.get('status')!='settled': raise self.runner.RunLimit('unknown_usage')
        self.validate_raw(raw)
        if self.config.get('interrupt_after_response') and not (self.out/'model-interruption.json').exists():
            write_json(self.out/'model-interruption.json',{'boundary':'response_saved','request_id':permit['request_id'],'pid':os.getpid()})
            os._exit(85)
        return response


def execute_case(config,case,run_dir,client,connection,*,resume=False):
    """The real run and scripted-API validation both call this production function."""
    runner=load_runtime(config)
    run=Path(run_dir);cid=case['id'];out=run/cid;fixture=Path(config['suite'])/'cases'/cid
    workspace=out/'workspace'
    if resume:
        preflight=inspect_native_case(config,case,out)
        if preflight['status'] not in ('ready','finished'):
            raise RuntimeError('needs_recovery:'+preflight['reason'])
    if not resume:
        import shutil
        shutil.copytree(fixture/'input',workspace)
    rpc=RPC(connection);guard=RequestGuard(runner,client,rpc,cid,out,config)
    adapter=runner.CaseAdapter(guard,out)
    checkpoint=runner.agent.checkpoints.CheckpointStore(out/'checkpoint')
    phases=json.loads((out/'phases.json').read_text(encoding='utf-8')) if resume and (out/'phases.json').exists() else []
    turn_path=out/'turn-state.json'
    turn=json.loads(turn_path.read_text(encoding='utf-8')) if resume and turn_path.exists() else None
    phase=turn['index'] if turn else (phases[-1]['index']+1 if resume and phases else 1)
    if type(phase) is not int or not 1<=phase<=len(case['turns']):
        raise RuntimeError('needs_recovery:invalid_turn_position')
    if turn and turn.get('user_input_sha256')!=sha256(case['turns'][phase-1].encode('utf-8')).hexdigest():
        raise RuntimeError('needs_recovery:turn_binding_changed')
    def emit(event):
        capture=event['type'] in ('tool_call','tool_result','final_response','assistant_candidate','verification')
        runner.append(out/'events.jsonl',{**event,'time':time.time(),'phase':phase,'files':runner.hashes(workspace) if capture else None})
    def ask(tool,args):
        reason=''
        if tool=='fetch_url' and (not service_url or args.get('url')!=service_url+'/fare'):reason='本题仅授权访问指定的本地服务。'
        if cid=='O09' and tool=='write_file' and runner.permissions.Workspace(workspace).resolve(args.get('path',''))==workspace.resolve()/'settings.json':
            reason='不授权覆盖 settings.json。可另存 settings.proposed.json。'
        result=('n',reason) if reason else ('y','')
        runner.append(out/'permissions.jsonl',{'phase':phase,'time':time.time(),'tool':tool,'decision':result[0],'path':args.get('path'),'url':args.get('url'),'reason':reason})
        return result
    policy=runner.permissions.PermissionManager(ask=ask,workspace=workspace)
    class RuntimeAgent(runner.agent.Agent):
        def _save_checkpoint(self):
            try:super()._save_checkpoint()
            except runner.agent.checkpoints.CheckpointError:
                self.checkpoint_storage_failure=True
                raise
            guard.checkpoint_saved()
    runtime=RuntimeAgent(guard,runner.tools.Toolset(policy.workspace,run_command=runner.MXC.run_command),
        permissions=policy,model_adapter=adapter,max_steps=runner.PARAMS['max_steps_per_turn'],event_sink=emit,
        checkpoint_store=checkpoint,**output_recovery_options(runner))
    adapter.runtime=runtime;guard.runtime=runtime
    if cid=='O08' and config.get('native_checkpoint_interrupt') and not resume:
        runner.arm_interruption(checkpoint,out,run)
    server=None;service_url='';start=time.monotonic()
    def record(result):
        if getattr(runtime,'checkpoint_storage_failure',False):
            raise RuntimeError('needs_recovery:checkpoint_storage_failure')
        entry={'index':phase,'text':result.text,'stop_reason':result.stop_reason}
        existing=next((p for p in phases if p['index']==phase),None)
        if existing is not None and existing!=entry:raise RuntimeError('needs_recovery:phase_result_conflict')
        if existing is None:phases.append(entry)
        runner.save(out/'phases.json',phases)
        import shutil
        dest=out/f'phase-{phase}'
        if not dest.exists():shutil.copytree(workspace,dest)
        checkpoint.acknowledge()
        write_json(turn_path,{'index':phase,'status':'recorded',
                             'user_input_sha256':sha256(case['turns'][phase-1].encode('utf-8')).hexdigest()})
    before=digest(Path(config['runtime_entry']))
    try:
        if cid=='O05':
            server,service_url=runner.start_service(out);_PORTS.add(server.server_port)
        verifier=runner.evaluator(case['module']).verification_hook(fixture,workspace) if cid=='O06' else None
        if resume:
            decision=runtime.inspect_checkpoint();runner.save(out/'resume-inspection.json',decision)
            if decision['status'] not in ('ready','finished'):raise RuntimeError('needs_recovery:'+decision['reason'])
            saved=checkpoint.load()
            previous_finished=(saved.get('synced') and turn and turn.get('status')=='running' and
                               phases and phase>phases[-1]['index'])
            result=runtime.resume()
            if previous_finished:next_phase=phase
            else:
                record(result)
                next_phase=phase+1 if result.stop_reason=='end_turn' else len(case['turns'])+1
            receipt=workspace/'receipt.txt'
            runner.save(out/'resume-after.json',{'pid':os.getpid(),
                'receipt_mtime_ns':receipt.stat().st_mtime_ns if receipt.is_file() else None})
        else:next_phase=1
        for phase in range(next_phase,len(case['turns'])+1):
            task=case['turns'][phase-1]
            write_json(turn_path,{'index':phase,'status':'running',
                                 'user_input_sha256':sha256(task.encode('utf-8')).hexdigest()})
            if phase==case.get('compact_at'):runner.trigger_compaction(runtime)
            result=runtime.run(task.replace('{{SERVICE_URL}}',service_url),verifier=verifier)
            record(result)
            if result.stop_reason!='end_turn':break
    finally:
        if server:server.shutdown();server.server_close()
        runner.save(out/'phases.json',phases);runner.save(out/'messages.json',runtime.messages)
        runner.save(out/'result.json',{'id':cid,'phases':phases,'seconds':time.monotonic()-start,
            'requests':json.loads((run/'budget.json').read_text())['per_case'].get(cid,0),'source_hashes':runner.hashes(workspace)})
    grade_source=Path(runner.evaluator(case['module']).__file__)
    grade_before=digest(grade_source)
    grade=runner.grade_case(case,fixture,out)
    binding={'agent_file':runner.agent.__file__,'tool_runner_file':runner.agent._tool_runner.__file__,
        'model_file':runner.agent.models.__file__,'native_executor_file':runner.MXC.__file__,
        'entry':config['runtime_entry'],'entry_sha256_before':before,'entry_sha256_after':digest(config['runtime_entry']),
        'grade_source':str(grade_source),'grade_sha256_before':grade_before,'grade_sha256_after':digest(grade_source),
        'transport':config['transport'],'validation':config.get('validation',False)}
    write_json(out/'runtime-binding.json',binding)
    return {'grade':grade,'runtime_binding':binding,'transport':config['transport']}


def real_worker_main(case,run_dir,connection,resume=False):
    config=case['_runtime_config'];out=Path(run_dir)/case['id'];out.mkdir(parents=True,exist_ok=True)
    rpc=RPC(connection)
    boundary=ValidationBoundary() if config.get('validation') else nullcontext()
    try:
        with boundary:
            rpc.call({'op':'ready','pid':os.getpid(),'resume':resume})
            if config['transport']=='scripted_api':
                client=ScriptedAPI(config.get('scripts_by_case',{}).get(case['id'],[]),out,config['model'])
            else: client=load_runtime(config).paid_client()
            result=execute_case(config,case,run_dir,client,connection,resume=resume)
            rpc.call({'op':'finished','result':result})
    except (Stopped,EOFError,BrokenPipeError,OSError): pass
    except Exception as error:
        write_json(out/'runtime-error.json',{'type':type(error).__name__,'reason':str(error)[:2000]})
        try:rpc.call({'op':'worker_error','reason':type(error).__name__+':'+str(error)[:600]})
        except (Stopped,EOFError,BrokenPipeError,OSError):pass
    finally:connection.close()


def inspect_native_case(config,case,out):
    """Run the original read-only schema/binding/verifier/tool recovery checks."""
    runner=load_runtime(config)
    out=Path(out)
    policy=runner.permissions.PermissionManager(ask=lambda *_:('n','preflight only'),workspace=out/'workspace')
    adapter=runner.CaseAdapter(None,out)
    runtime=runner.agent.Agent(None,runner.tools.Toolset(policy.workspace,run_command=runner.MXC.run_command),
        permissions=policy,model_adapter=adapter,max_steps=runner.PARAMS['max_steps_per_turn'],
        checkpoint_store=runner.agent.checkpoints.CheckpointStore(out/'checkpoint'),**output_recovery_options(runner))
    adapter.runtime=runtime
    decision=runtime.inspect_checkpoint()
    if decision['status'] not in ('ready','finished'):return decision
    native=runtime.checkpoint_store.load()
    if native.get('run_state',{}).get('request_inflight') in ('model','summary'):
        # A saved SDK response may never become a new paid physical request just
        # because the local pending identity was lost or altered.
        identity=out/'response-state.json';ledger=out.parent/'request-ledger.jsonl'
        if not identity.is_file() or not ledger.is_file():
            return {'status':'blocked','reason':'Saved request identity or durable ledger is missing'}
        pending=json.loads(identity.read_text(encoding='utf-8'))
        with ledger.open(encoding='utf-8') as stream:
            last=None
            for line in stream:last=line
        snapshot=json.loads(last) if last else {}
        matches=[r for r in snapshot.get('records',[]) if r.get('request_id')==pending.get('request_id')]
        if (pending.get('consumed') or len(matches)!=1 or matches[0].get('case_id')!=case['id'] or
                matches[0].get('attempt_id')!=pending.get('attempt_id') or matches[0].get('status')!='settled' or
                matches[0].get('consumed') or not matches[0].get('response_recorded') or
                matches[0].get('payload_sha256')!=pending.get('payload_sha256')):
            return {'status':'blocked','reason':'Saved request identity does not match the unconsumed durable response'}
    turn_path=out/'turn-state.json'
    if turn_path.exists():
        turn=json.loads(turn_path.read_text(encoding='utf-8'));index=turn.get('index')
        if (type(index) is not int or not 1<=index<=len(case['turns']) or
                turn.get('user_input_sha256')!=sha256(case['turns'][index-1].encode('utf-8')).hexdigest()):
            return {'status':'blocked','reason':'Native turn position or task binding differs'}
    return decision


def inspect_run(run_dir):
    run=Path(run_dir)
    if (run/'summary.json').exists():
        d=json.loads((run/'summary.json').read_text(encoding='utf-8'))
        if d.get('complete'):return {'status':'finished'}
    if not (run/'request-ledger.jsonl').exists():return {'status':'needs_recovery','reason':'No durable request ledger'}
    cfg=json.loads((run/'config.json').read_text(encoding='utf-8'))
    validate_binding(cfg)
    budget=json.loads((run/'budget.json').read_text(encoding='utf-8'))
    if budget.get('unknown_requests') or budget.get('inflight_requests'):
        return {'status':'needs_recovery','reason':'Unresolved physical requests remain; no automatic resend'}
    if budget.get('halt')!='checkpoint_paused':
        return {'status':'needs_recovery','reason':budget.get('halt') or 'Explicit native checkpoint inspection required'}
    checkpoints=[]
    try:
        for case in load_cases(cfg,cfg['case_ids']):
            folder=run/case['id'];worker=folder/'worker-state.json'
            if worker.exists() and json.loads(worker.read_text(encoding='utf-8')).get('status')=='completed':continue
            checkpoint=folder/'checkpoint/default.json'
            if not checkpoint.exists():
                if (folder/'workspace').exists():
                    return {'status':'needs_recovery','reason':'Started case has no trusted native checkpoint: '+case['id']}
                continue
            decision=inspect_native_case(cfg,case,folder)
            if decision['status'] not in ('ready','finished'):
                return {'status':'needs_recovery','reason':case['id']+': '+decision['reason']}
            checkpoints.append(case['id'])
    except (OSError,ValueError,TypeError,KeyError) as error:
        return {'status':'needs_recovery','reason':'Native recovery preflight failed: '+type(error).__name__}
    if not checkpoints:return {'status':'needs_recovery','reason':'No trusted native checkpoint to resume'}
    return {'status':'checkpoint_paused','cases':checkpoints,'reason':'All native recovery checks passed before reopening the batch'}


def freeze_plan(config,path):
    """Freeze paths/limits before approval, without creating a client or running a task."""
    policy=output_policy(config)
    result={**default_binding(),'workers':2,'max_inflight_requests':2,'request_interval':0,
            'budget_limit':'30','max_requests':1200,'max_requests_per_case':60,'case_timeout':120,
            'max_retries':0,'prompt_price_per_million':'2','output_price_per_million':'8',**config}
    if policy and 'case_timeout' not in config:
        result['case_timeout']=max(120,policy['timeout']+30)
    if 'max_inflight_requests' not in config:result['max_inflight_requests']=result['workers']
    if result['runtime_entry_sha256']!=digest(result['runtime_entry']):raise ValueError('runtime fingerprint changed')
    if not result.get('case_ids'):raise ValueError('Explicit case_ids required')
    load_cases(result,result['case_ids'])
    result['effective_parameters']=effective_parameters(result)
    result['binding_files']=execution_files(result)
    if Path(path).exists():raise FileExistsError('Frozen plan already exists')
    write_json(path,result)
    return digest(path)


def resume_run(plan,run_dir):
    from formal20_concurrent import run_batch
    from formal20_start_guard import execution_lock
    run=Path(run_dir).resolve()
    with execution_lock(run):
        saved=json.loads((run/'config.json').read_text(encoding='utf-8'))
        for key,value in plan.items():
            if key!='out' and saved.get(key)!=value:raise ValueError('Resume binding changed: '+key)
        decision=inspect_run(run)
        if decision['status']=='finished':return json.loads((run/'summary.json').read_text(encoding='utf-8'))
        if decision['status']!='checkpoint_paused':raise ValueError('needs_recovery: '+decision['reason'])
        return run_batch({**saved,'out':str(run),'_resume':True},load_cases(saved,saved['case_ids']))
