"""终端入口：本机初始化、命令交互与会话保存。"""
import os
import math
from contextlib import nullcontext
from uuid import uuid4
from urllib.parse import urlsplit

from agent import Agent, MODEL, MAX_STEPS, models, checkpoints
from context import SessionStore
from mcp_adapter import MCPStartupError, open_mcp
from permissions import PermissionManager, Workspace
from prompts import SYSTEM
from tools import Toolset


def limit_setting(name, default, parse):
    try:
        value = parse(os.environ.get(name, str(default)))
        if value < 0 or (parse is float and not math.isfinite(value)):
            raise ValueError()
        return value
    except ValueError:
        raise ValueError(f'{name} 必须是非负{"整数" if parse is int else "有限数"}，0 表示关闭') from None


def create_agent(*, mcp=None, workspace=None):
    # 只有启动真实程序时读取现有密钥并创建 SDK 客户端。
    steps = limit_setting('AGENT_STEP_LIMIT', MAX_STEPS, int)
    tokens = limit_setting('AGENT_TOKEN_LIMIT', 0, int)
    seconds = limit_setting('AGENT_TIME_LIMIT_SECONDS', 0, float)
    provider = os.environ.get('MODEL_PROVIDER', 'deepseek')
    config = models.ModelConfig(
        provider=provider,
        model_name=os.environ.get('MODEL', MODEL if provider == 'deepseek' else ''),
        base_url=os.environ.get('BASE_URL', models.DEEPSEEK_BASE_URL if provider == 'deepseek' else None))
    models.validate_config(config)
    key_env = os.environ.get('MODEL_API_KEY_ENV')
    address = urlsplit(config.base_url or '')
    trusted_default = (provider == 'deepseek' and address.scheme == 'https' and
                       address.hostname == 'api.deepseek.com' and address.port in (None, 443))
    if provider == 'openai_chat' and (not config.base_url or not key_env):
        raise ValueError('openai_chat 必须明确配置 MODEL、BASE_URL 和 MODEL_API_KEY_ENV')
    if not trusted_default and not key_env:
        raise ValueError('自定义模型地址必须明确配置 MODEL_API_KEY_ENV，不自动沿用 DeepSeek 密钥')
    if key_env:
        api_key = os.environ.get(key_env)
        if not api_key:
            raise ValueError(f'未配置密钥环境变量：{key_env}')
    else:
        api_key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('API_KEY')
        if not api_key:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as env:
                api_key = winreg.QueryValueEx(env, 'DEEPSEEK_API_KEY')[0]
    adapter = models.get_model(config, api_key=api_key)
    if workspace is None:
        workspace = Workspace(os.environ.get("NAMI_WORKSPACE", os.getcwd()))
    permissions = (PermissionManager(workspace=workspace, mcp_read_only=mcp.read_only_tools)
                   if mcp is not None else None)
    return Agent(adapter.client, Toolset(workspace, mcp=mcp), permissions=permissions,
                 model=config.model_name, model_adapter=adapter,
                 max_steps=steps or None, token_limit=tokens, wall_time_limit_seconds=seconds)


def handle_auto(args, perms):
    """处理 /auto 的状态查询、开关参数和用法提示。"""
    if not args:
        print(f"自动执行：{'已开启' if perms.auto_approve else '已关闭'}。\n")
    elif len(args) == 1 and args[0] in ("on", "off"):
        perms.set_auto_approve(args[0] == "on")
        if perms.auto_approve:
            print("自动执行已开启。已登记的原生工具免确认，MCP 工具按本地权限配置确认。\n")
        else:
            print("自动执行已关闭：需确认的工具恢复询问，已清除本次记住的工具授权。\n")
    else:
        print("用法：/auto on、/auto off，或 /auto 查看状态。\n")


def start_new_session(agent, store):
    """先备份、保存，再切换上下文；保留 token 累计与权限状态。"""
    cp = agent.checkpoint_store
    with cp.lease() if cp is not None else nullcontext():
        original = agent.messages
        if cp is not None:
            try:
                saved = cp.load()
            except checkpoints.CheckpointError:
                saved = None
            if cp.pending(saved):
                original = saved['messages']
            cp.archive()
        backup_name = f"default-backup-{uuid4().hex}"
        fresh = [{"role": "system", "content": SYSTEM}]
        store.save(backup_name, original)
        store.save("default", fresh)
        if cp is not None:
            try:
                cp.new_session()
            except checkpoints.CheckpointError:
                store.save('default', original)
                raise
        agent.messages = fresh
        agent.last_prompt_tokens = 0   # 只重置压缩依据，不清零 token 累计。
        print(f"已开始新会话；旧会话已备份为 {backup_name}.json；token 累计保留。\n")


def sync_session(agent, store):
    store.save('default', agent.messages)
    cp = agent.checkpoint_store
    if cp is not None:
        saved = cp.load()
        if (saved and saved['status'] == 'run' and saved['run_state']['next_action'] == 'finished'
                and saved['run_state']['run_id'] == agent.run_state.run_id):
            cp.acknowledge()


def handle_resume(agent, store):
    result = agent.resume()
    print('\n' + result.text + '\n')
    cp = agent.checkpoint_store
    if cp is not None:
        saved = cp.load()
        if (saved and saved['status'] == 'run' and saved['run_state']['run_id'] == agent.run_state.run_id):
            sync_session(agent, store)


def recovery_pending(agent):
    if agent.checkpoint_store is None:
        return False
    try:
        return agent.checkpoint_store.pending(agent.checkpoint_store.load())
    except checkpoints.CheckpointError:
        return True


def main(agent=None, store=None):
    terminal = agent is None
    config_path = os.environ.get("NAMI_MCP_CONFIG") if terminal else None
    workspace = Workspace(os.environ.get("NAMI_WORKSPACE", os.getcwd())) if config_path else None
    connection = open_mcp(config_path, workspace=workspace.root) if config_path else nullcontext()
    try:
        with connection as mcp:
            if terminal:
                agent = create_agent(mcp=mcp, workspace=workspace)
            if mcp is not None:
                print("已加载 MCP 工具 " + ", ".join(mcp.tools))
            run_session(agent, store, terminal=terminal)
    except MCPStartupError as error:
        raise SystemExit(str(error)) from error


def run_session(agent, store, *, terminal):
    store = store if store is not None else SessionStore()
    if terminal and agent.checkpoint_store is None:
        agent.checkpoint_store = checkpoints.CheckpointStore(store.directory.parent / 'checkpoints')
    cp = agent.checkpoint_store
    with cp.lease() if cp is not None else nullcontext():
        agent.messages = store.load("default") or [{"role": "system", "content": SYSTEM}]
        if agent.event_sink is None:
            agent.event_sink = lambda event: store.append_event("default", event)
        if cp is not None:
            cp.trace_path = store.directory / 'default.trace.jsonl'
            if recovery_pending(agent):
                print('检测到未同步检查点：' + agent.inspect_checkpoint()['reason'])
        print("自动执行默认关闭；/auto on 开启，/auto off 关闭，/auto 查看状态。")
        interact(agent, store)


def interact(agent, store):
    while True:
        q = input("你> ").strip()
        if q in ("exit", "quit"):
            break
        command = q.split()
        if command and command[0] == "/auto":
            handle_auto(command[1:], agent.permissions)
            continue
        if q == "/new":
            start_new_session(agent, store)
            continue
        if q == '/resume':
            handle_resume(agent, store)
            continue
        if recovery_pending(agent):
            print('存在未完成检查点，请先 /resume 或 /new；尚未请求模型。')
            continue
        try:
            result = agent.run(q)
            print("\n" + result.text + "\n")
        finally:
            sync_session(agent, store)


