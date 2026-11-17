"""Isolated synthetic worker and guarded adapter for the frozen single-case entry."""
from __future__ import annotations

from contextlib import AbstractContextManager
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

_BOUNDARY_DEPTH = 0
_AUDIT_INSTALLED = False
_ENV_GETITEM = os._Environ.__getitem__
_ENV_COPY = os._Environ.copy
_PROCESS_MARKER = None


def _audit(event, args):
    if not _BOUNDARY_DEPTH:
        return
    if event.startswith('socket.') or event.startswith('winreg.'):
        raise PermissionError('Offline simulation forbids network and registry access')
    if event == 'import':
        name = args[0]
        if name.split('.')[0] in ('openai', 'anthropic', 'httpx', 'requests', 'boundary_common') or name.startswith(('grade-', 'formal-', 'run-formal-')):
            raise PermissionError('Offline simulation forbids model SDKs and original scorers')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        value = os.fsdecode(args[0]).replace('\\', '/').lower()
        if '/judge-only/' in value or '/harness-formal-20-v0.2/' in value or '/harness-v0.40-formal20-20261115/' in value or '/new-chat-5/work/' in value:
            raise PermissionError('Offline simulation cannot open original task or scorer materials')


def _credential_name(key):
    name = os.fsdecode(key).upper()
    return any(s in name for s in ('API_KEY','PASSWORD','SECRET','ACCESS_TOKEN')) or name.endswith('_TOKEN')


def _env_getitem(env, key):
    if _BOUNDARY_DEPTH and _credential_name(key):
        raise PermissionError('Offline simulation cannot read credentials')
    return _ENV_GETITEM(env, key)


def _env_copy(env):
    # Windows venv spawning copies the environment: omit sensitive names before reading values.
    return {key: env[key] for key in env if not _credential_name(key)}


class OfflineBoundary(AbstractContextManager):
    def __enter__(self):
        global _BOUNDARY_DEPTH, _AUDIT_INSTALLED
        if not _AUDIT_INSTALLED:
            sys.addaudithook(_audit)
            _AUDIT_INSTALLED = True
        _BOUNDARY_DEPTH += 1
        os._Environ.__getitem__ = _env_getitem
        os._Environ.copy = _env_copy
        return self

    def __exit__(self, *args):
        global _BOUNDARY_DEPTH
        _BOUNDARY_DEPTH -= 1
        if not _BOUNDARY_DEPTH:
            os._Environ.__getitem__ = _ENV_GETITEM
            os._Environ.copy = _ENV_COPY


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


class Stopped(RuntimeError):
    pass


class RPC:
    def __init__(self, connection):
        self.connection = connection

    def call(self, message):
        self.connection.send(message)
        reply = self.connection.recv()
        if reply.get('status') in ('halted', 'case_limit'):
            raise Stopped(reply.get('reason', reply['status']))
        return reply


def worker_main(case, run_dir, connection, resume=False):
    """A fresh spawn process owns this case only; no SDK or original module import."""
    global _PROCESS_MARKER
    _PROCESS_MARKER = case['id']
    out = Path(run_dir)/case['id']
    workspace = out/'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    rpc = RPC(connection)
    def event(kind, **data):
        with (out/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'kind':kind,'pid':os.getpid(),'time':time.monotonic(),**data})+'\n')
    try:
        with OfflineBoundary():
            rpc.call({'op':'ready','pid':os.getpid(),'resume':resume})
            # Each process exercises the same explicit offline boundaries.
            for action in (lambda: os.getenv('DASHSCOPE_API_KEY'), lambda: __import__('openai')):
                try: action()
                except PermissionError: pass
                else: raise RuntimeError('offline boundary bypassed')
            kind = case.get('kind','normal')
            if kind=='legacy_probe':
                raw={'model':case.get('probe_response_model','offline-scripted'),
                     'usage':{'prompt_tokens':100,'completion_tokens':10},'choices':[{'message':{}}]}
                client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                    create=lambda **_: SimpleNamespace(model_dump=lambda **_: raw))))
                result=run_legacy_probe(case['source_entry'],case['source_sha256'],case,out,out,connection,client)
                write_json(workspace/'result.json',result)
                rpc.call({'op':'finished','result':result})
                return
            steps = [2] if resume else ([1] if kind in ('checkpoint','one_request') else [1,2])
            if resume:
                saved = json.loads((out/'checkpoint.json').read_text(encoding='utf-8'))
                if (saved['boundary']!='recorded' or (workspace/'receipt.txt').read_text(encoding='utf-8')!='recorded-once'
                        or (workspace/'receipt.txt').stat().st_mtime_ns!=saved['receipt_mtime_ns']):
                    raise RuntimeError('invalid checkpoint')
            for step in steps:
                permit = rpc.call({'op':'acquire','attempt_id':str(step),'reserve_cost':case.get('reserve_cost','0.006'),
                                  'prompt_metadata':{'payload':{'model':'offline-scripted','step':step}}})
                event('request_started',request_id=permit['request_id'],step=step)
                if kind=='crash': os._exit(77)
                if kind=='disconnect':
                    connection.close()
                    time.sleep(3600)
                if kind=='unexpected_checkpoint': os._exit(86)
                if kind=='timeout': time.sleep(3600)
                time.sleep(case.get('delay',.03))
                if kind=='api_error':
                    rpc.call({'op':'api_error','request_id':permit['request_id'],'reason':'simulated_api_error'})
                    raise Stopped('simulated_api_error')
                usage = {'prompt_tokens':100,'completion_tokens':10}
                if kind=='unknown_usage': usage={}
                reply = rpc.call({'op':'settle','request_id':permit['request_id'],'usage':usage,
                                 'response_metadata':{'body':{'model':'offline-scripted','usage':usage}}})
                if reply.get('status')!='settled': raise Stopped('unknown_usage')
                event('request_settled',step=step)
            if kind=='checkpoint' and not resume:
                with (workspace/'receipt.txt').open('x',encoding='utf-8') as stream: stream.write('recorded-once')
                event('receipt_written')
                record = {'boundary':'recorded','receipt_sha256':sha256((workspace/'receipt.txt').read_bytes()).hexdigest(),
                          'receipt_mtime_ns':(workspace/'receipt.txt').stat().st_mtime_ns}
                write_json(out/'checkpoint.json',record)
                rpc.call({'op':'checkpoint',**record,'halt_after_ack':case.get('halt_at_checkpoint',False)})
                time.sleep(case.get('pause_before_exit',0))
                connection.close()
                os._exit(86)
            recorded=[json.loads(line) for line in (out/'events.jsonl').read_text(encoding='utf-8').splitlines()]
            writes=sum(e['kind']=='receipt_written' for e in recorded)
            result = {'owner':case['id'],'process_marker':_PROCESS_MARKER,
                      'steps':[e['step'] for e in recorded if e['kind']=='request_settled'],
                      'receipt_writes':writes,'backend':'synthetic'}
            write_json(workspace/'result.json',result)
            rpc.call({'op':'finished','result':result})
    except (Stopped, EOFError, BrokenPipeError, ConnectionError, OSError) as error:
        event('stopped',reason=type(error).__name__)
    except Exception as error:
        try: rpc.call({'op':'worker_error','reason':type(error).__name__})
        except (EOFError, BrokenPipeError, OSError, Stopped): pass
        event('worker_error',reason=type(error).__name__)
    finally:
        connection.close()


def run_legacy_probe(source_entry, expected_sha256, case, suite, run, connection, client):
    """Exercise the adapter only with an explicit synthetic module, never the real entry."""
    entry = Path(source_entry)
    if entry.name != 'synthetic_entry.py' or not case['id'].startswith('SIM-'):
        raise PermissionError('Real evaluation execution is disabled in this release')
    with OfflineBoundary():
        if sha256(entry.read_bytes()).hexdigest()!=expected_sha256:
            raise ValueError('source entry fingerprint changed')
        spec = importlib.util.spec_from_file_location('_formal20_synthetic_probe', entry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if getattr(module,'OFFLINE_PROBE',False) is not True:
            raise PermissionError('Only the synthetic adapter probe is permitted')
        rpc = RPC(connection)
        class RequestGuard:
            def __init__(self, client, run, cid):
                self.client,self.cid,self.attempt = client,cid,0
                self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
            def create(self, **payload):
                self.attempt+=1
                if payload.get('model')!=module.PARAMS['model'] or payload.get('extra_body',{})!=module.PARAMS['adapter_body']:
                    rpc.call({'op':'configuration_error','reason':'model_configuration_drift'})
                    raise Stopped('model_configuration_drift')
                payload['extra_body']=module.PARAMS['request_body'].copy()
                payload['max_tokens']=module.PARAMS['max_tokens']
                reserve=module.cost(len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))+16384,module.PARAMS['max_tokens'])
                permit=rpc.call({'op':'acquire','attempt_id':str(self.attempt),'reserve_cost':str(reserve),'prompt_metadata':{'payload':payload}})
                try: response=self.client.chat.completions.create(**payload)
                except Exception:
                    rpc.call({'op':'api_error','request_id':permit['request_id'],'reason':'probe_error'})
                    raise
                raw=response.model_dump(mode='json',exclude_none=True,warnings=False)
                reply=rpc.call({'op':'settle','request_id':permit['request_id'],'usage':raw.get('usage'),'response_metadata':{'body':raw}})
                if reply.get('status')!='settled': raise Stopped('unknown_usage')
                reason=None
                if raw.get('model')!=module.PARAMS['model']: reason='response_model_mismatch'
                details=(raw.get('usage') or {}).get('completion_tokens_details',{})
                if details and details.get('reasoning_tokens'): reason='thinking_mode_mismatch'
                if any(c.get('message',{}).get('reasoning_content') for c in raw.get('choices',[]) if isinstance(c,dict)):
                    reason='thinking_mode_mismatch'
                if reason:
                    rpc.call({'op':'configuration_error','reason':reason})
                    raise Stopped(reason)
                return response
        module.RequestGuard=RequestGuard
        return module.execute_case(case,Path(suite),Path(run),client)
