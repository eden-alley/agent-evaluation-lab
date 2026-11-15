"""执行检查点：JSON 存储、独占租约和恢复校验；不调用模型或工具。"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

from context import atomic_write_json, render_tool_result
from tools import ToolResult
from verification import CheckResult
from .state import RunResult, RunState
from .model_openai import _message

SCHEMA_VERSION = 1


class CheckpointError(RuntimeError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def binding(runtime):
    source = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(Path(__file__).parent.glob('*.py'))}
    model = runtime.model_adapter
    config = getattr(model, 'config', None)
    address = getattr(config, 'base_url', None) or getattr(runtime.client, 'base_url', '')
    tools = runtime.tools.get_schemas()
    mcp = getattr(runtime.tools, 'mcp', None)
    if mcp is not None:
        tools = {'schemas': tools, 'mcp': mcp.binding}
    return {
        'source': _digest(source),
        'workspace': os.path.normcase(str(runtime.tools.workspace.root.resolve())),
        'tools': _digest(tools),
        'model': {'provider': getattr(config, 'provider', 'deepseek'),
                  'model_name': getattr(config, 'model_name', runtime.model),
                  'endpoint_hash': hashlib.sha256(str(address).rstrip('/').encode('utf-8')).hexdigest()},
        'limits': {'max_steps': runtime.max_steps, 'soft_limit': runtime.soft_limit,
                   'hard_limit': runtime.hard_limit, 'token_limit': runtime.token_limit,
                   'wall_time_limit_seconds': runtime.wall_time_limit_seconds},
    }


def capture(runtime, session_id, runtime_binding):
    state = runtime.run_state
    usage = {'owner': runtime._usage_owner, 'totals': deepcopy(runtime.token_usage.totals),
             'incomplete': runtime.token_usage.incomplete}
    state.usage_history[:] = [item for item in state.usage_history if item['owner'] != usage['owner']]
    state.usage_history.append(usage)
    return {'schema_version': SCHEMA_VERSION, 'session_id': session_id, 'status': 'run',
            'synced': False, 'revision': 0, 'binding': runtime_binding,
            'messages': deepcopy(runtime.messages), 'last_prompt_tokens': runtime.last_prompt_tokens,
            'run_state': asdict(state)}


def validate(snapshot):
    if (not isinstance(snapshot, dict) or type(snapshot.get('schema_version')) is not int
            or snapshot['schema_version'] != SCHEMA_VERSION):
        raise ValueError('不支持的检查点版本或损坏的检查点')
    if not isinstance(snapshot.get('session_id'), str) or not re.fullmatch('[0-9a-f]{32}', snapshot['session_id']):
        raise ValueError('检查点会话编号无效')
    if snapshot.get('status') == 'idle':
        if set(snapshot) != {'schema_version', 'session_id', 'status', 'synced', 'revision'} or snapshot['synced'] is not True:
            raise ValueError('空闲检查点混入执行数据')
        return
    if type(snapshot.get('revision')) is not int or snapshot['revision'] < 0:
        raise ValueError('检查点版本计数无效')
    if snapshot.get('status') != 'run' or type(snapshot.get('synced')) is not bool:
        raise ValueError('检查点状态无效')
    state = snapshot.get('run_state')
    if not isinstance(state, dict) or set(state) != {item.name for item in fields(RunState)}:
        raise ValueError('检查点运行字段无效')
    if not isinstance(state['run_id'], str) or not re.fullmatch('[0-9a-f]{32}', state['run_id']):
        raise ValueError('检查点运行编号无效')
    for key in ('steps_used', 'verification_attempts', 'last_event_id', 'limit_tokens_used'):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError(f'检查点 {key} 无效')
    if type(state['limit_usage_incomplete']) is not bool:
        raise ValueError('检查点限额用量标记无效')
    started = state['limit_started_at']
    if started is not None and (type(started) not in (int, float) or not math.isfinite(started) or started < 0):
        raise ValueError('检查点开始时间无效')
    bound = snapshot.get('binding')
    if not isinstance(bound, dict) or not isinstance(bound.get('limits'), dict):
        raise ValueError('检查点恢复配置无效')
    if bound['limits'].get('wall_time_limit_seconds') and started is None:
        raise ValueError('检查点缺少原始开始时间')
    if state['next_action'] not in ('prepare', 'summary', 'request', 'response', 'tools', 'candidate', 'finished'):
        raise ValueError('检查点执行位置无效')
    if snapshot['synced'] and state['next_action'] != 'finished':
        raise ValueError('未完成检查点不能标为已同步')
    if state['request_inflight'] not in (None, 'model', 'summary', 'verification'):
        raise ValueError('检查点模型请求状态无效')
    request_positions = {'model': 'request', 'summary': 'summary', 'verification': 'candidate'}
    if state['request_inflight'] and request_positions[state['request_inflight']] != state['next_action']:
        raise ValueError('检查点请求与执行位置不一致')
    if type(state['requires_verifier']) is not bool or not isinstance(snapshot.get('binding'), dict):
        raise ValueError('检查点恢复配置无效')
    messages = snapshot.get('messages')
    if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) for m in messages):
        raise ValueError('检查点消息无效')
    if type(snapshot.get('last_prompt_tokens')) is not int or snapshot['last_prompt_tokens'] < 0:
        raise ValueError('检查点上下文用量无效')
    for key in ('events', 'tool_results', 'usage_history', 'unknown_usage', 'active_batch'):
        if not isinstance(state[key], list):
            raise ValueError(f'检查点 {key} 无效')
    for item in state['usage_history']:
        if not isinstance(item, dict) or not isinstance(item.get('owner'), str) or type(item.get('incomplete')) is not bool:
            raise ValueError('检查点历史用量无效')
        if not isinstance(item.get('totals'), dict) or any(
                type(item['totals'].get(key)) is not int or item['totals'][key] < 0
                for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')):
            raise ValueError('检查点历史用量字段无效')
    if state['next_action'] == 'response' and (not isinstance(state['response'], dict) or
            not {'message', 'protocol_error'} <= state['response'].keys() or
            (state['response']['protocol_error'] is None and not isinstance(state['response']['message'], dict))):
        raise ValueError('检查点缓存回复无效')
    if state['next_action'] == 'response':
        response = state['response']
        if response['protocol_error'] is None:
            _message(response['message'], tools_allowed=True)
        elif not isinstance(response['protocol_error'], str) or not response['protocol_error']:
            raise ValueError('检查点协议错误记录无效')
    if state['next_action'] == 'candidate' and not isinstance(state['candidate'], str):
        raise ValueError('检查点候选回答无效')
    records = state['call_records']
    if not isinstance(records, dict) or not isinstance(state['pending_calls'], dict):
        raise ValueError('检查点调用记录无效')
    if len(set(state['active_batch'])) != len(state['active_batch']) or any(k not in records for k in state['active_batch']):
        raise ValueError('检查点工具批次无效')
    if state['next_action'] == 'tools' and not state['active_batch']:
        raise ValueError('检查点缺少当前工具批次')
    for record in records.values():
        call = record.get('call') if isinstance(record, dict) else None
        if not isinstance(call, dict) or not isinstance(call.get('id'), str):
            raise ValueError('检查点原始调用无效')
        function = call.get('function')
        if not isinstance(function, dict) or not isinstance(function.get('name'), str) or not isinstance(function.get('arguments'), str):
            raise ValueError('检查点工具参数无效')
        if record.get('status') not in ('pending', 'executing', 'recorded'):
            raise ValueError('检查点工具状态无效')
        if record['status'] == 'recorded' and not isinstance(record.get('result'), dict):
            raise ValueError('检查点缺少真实工具结果')
        if record['status'] == 'recorded':
            result = record['result']
            if (result.get('call_id') != call['id'] or result.get('tool') != function['name'] or
                    result.get('source') != record.get('source') or result not in state['tool_results']):
                raise ValueError('检查点工具结果与调用不一致')
    pending = {}
    for message in messages:
        if message.get('role') == 'tool':
            call_id = message.get('tool_call_id')
            if call_id not in pending or not isinstance(message.get('content'), str):
                raise ValueError('检查点工具消息配对无效')
            pending.pop(call_id)
        else:
            if pending:
                raise ValueError('检查点工具批次缺少结果')
            for call in message.get('tool_calls') or []:
                if call['id'] in pending:
                    raise ValueError('检查点工具 ID 重复')
                pending[call['id']] = call
    if pending != state['pending_calls']:
        raise ValueError('检查点消息与待执行调用不一致')
    unfinished = {record['call']['id']: record['call'] for key, record in records.items()
                  if record['source'] == 'model' and record['status'] != 'recorded'}
    if unfinished != state['pending_calls']:
        raise ValueError('检查点调用状态与待执行列表不一致')
    batch_pending = {records[key]['call']['id']: records[key]['call'] for key in state['active_batch']
                     if records[key]['status'] != 'recorded'}
    if batch_pending != unfinished or (unfinished and state['next_action'] != 'tools'):
        raise ValueError('检查点调用缺少对应执行位置')
    for key in state['active_batch']:
        record = records[key]
        if record['source'] != 'model':
            raise ValueError('检查点执行批次来源无效')
        if record['status'] == 'recorded':
            result = {k: v for k, v in record['result'].items() if k not in ('call_id', 'tool', 'source')}
            expected = render_tool_result(ToolResult(**result))
            if not any(m.get('role') == 'tool' and m.get('tool_call_id') == record['call']['id']
                       and m.get('content') == expected for m in messages):
                raise ValueError('检查点已记录结果缺少工具消息')
    if state['next_action'] == 'finished' and (not isinstance(state['result'], dict) or
            messages[-1].get('content') != state['result'].get('text')):
        raise ValueError('检查点最终回答不一致')
    json.dumps(snapshot, allow_nan=False)


def restore_state(data):
    data = deepcopy(data)
    if data['verification'] is not None:
        data['verification'] = CheckResult(**data['verification'])
    if data['result'] is not None:
        result = data['result']
        verification = CheckResult(**result['verification']) if result['verification'] is not None else None
        data['result'] = RunResult(result['text'], result['stop_reason'], verification)
    return RunState(**data)


class CheckpointStore:
    def __init__(self, directory, session_name='default', *, trace_path=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', session_name):
            raise ValueError('检查点名称无效')
        self.directory = Path(directory)
        self.path = self.directory / f'{session_name}.json'
        self.lock_path = self.directory / f'{session_name}.lock'
        self.trace_path = Path(trace_path) if trace_path is not None else None
        self._thread_lock = threading.RLock()
        self._depth = 0

    @contextmanager
    def lease(self):
        if not self._thread_lock.acquire(blocking=False):
            raise CheckpointError('检查点正被另一个执行者占用')
        stream = None
        try:
            if not self._depth:
                self.directory.mkdir(parents=True, exist_ok=True)
                stream = self.lock_path.open('a+b')
                if stream.tell() == 0:
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise CheckpointError('检查点正被另一个进程占用') from None
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
        except OSError as error:
            raise CheckpointError(f'检查点存储失败：{error}') from error
        finally:
            if stream is not None:
                stream.close()  # OS 锁随句柄关闭释放；硬退出也不会留下逻辑死锁。
            self._thread_lock.release()

    def load(self):
        try:
            if not self.path.exists():
                return None
            snapshot = json.loads(self.path.read_text(encoding='utf-8'))
            validate(snapshot)
            return snapshot
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CheckpointError(f'检查点无法读取：{error}') from error

    def save(self, snapshot):
        try:
            validate(snapshot)
            with self.lease():
                payload = deepcopy(snapshot)
                revision = 0
                if self.path.exists():
                    try:
                        previous = json.loads(self.path.read_text(encoding='utf-8'))
                        revision = previous.get('revision', 0)
                        if type(revision) is not int or revision < 0:
                            raise ValueError('检查点版本计数无效')
                    except (ValueError, TypeError, AttributeError):
                        if snapshot['status'] != 'idle':
                            raise CheckpointError('旧检查点损坏，请先 /new 备份归档') from None
                        revision = 0
                payload['revision'] = revision + 1
                atomic_write_json(self.path, payload)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CheckpointError(f'检查点保存失败：{error}') from error

    @staticmethod
    def pending(snapshot):
        return bool(snapshot and snapshot['status'] == 'run' and not snapshot['synced'])

    def archive(self):
        try:
            snapshot = self.load()
        except CheckpointError:
            try:
                atomic_write_json(self.directory / 'archive' / f'invalid-{uuid4().hex}.json',
                                  {'unreadable_bytes_hex': self.path.read_bytes().hex()})
            except OSError as error:
                raise CheckpointError(f'损坏检查点备份失败：{error}') from error
            return
        if snapshot and snapshot['status'] == 'run':
            try:
                atomic_write_json(self.directory / 'archive' / f"{snapshot['run_state']['run_id']}.json", snapshot)
            except OSError as error:
                raise CheckpointError(f'检查点归档失败：{error}') from error

    def acknowledge(self):
        with self.lease():
            snapshot = self.load()
            if snapshot and snapshot['status'] == 'run':
                if snapshot['run_state']['next_action'] != 'finished':
                    raise CheckpointError('未完成的任务不能确认同步完成')
                snapshot['synced'] = True
                try:
                    atomic_write_json(self.directory / 'archive' / f"{snapshot['run_state']['run_id']}.json", snapshot)
                except OSError as error:
                    raise CheckpointError(f'检查点归档失败：{error}') from error
                self.save(snapshot)

    def new_session(self):
        self.save({'schema_version': SCHEMA_VERSION, 'session_id': uuid4().hex,
                   'status': 'idle', 'synced': True, 'revision': 0})

    def trace_event_floor(self, run_id):
        highest = 0
        if self.trace_path is not None and self.trace_path.exists():
            with self.trace_path.open('rb') as stream:
                for line in stream:
                    try:
                        event = json.loads(line.decode('utf-8'))
                    except (UnicodeError, ValueError):
                        continue  # 轨迹不是恢复依据，只跳过不完整的审计行。
                    if isinstance(event, dict) and event.get('run_id') == run_id and type(event.get('event_id')) is int:
                        highest = max(highest, event['event_id'])
        return highest
