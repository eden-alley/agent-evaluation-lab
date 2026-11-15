# Harness Evolution

一个面向真实任务、持续演进的 Python Agent harness。项目关注模型调用之外的执行工程：
工具契约、权限边界、运行状态、检查点、上下文、资源限制与可复查的执行证据。

目标是构建一个小而完整、容易扩展、行为可验证的基础内核。每次改动需要说明解决了什么问题，
通过可复现测试和版本对照留下依据。当前为单机、同步、Windows 优先的实现，可靠性边界仍在逐项完善。

## 已实现的能力

- **执行循环**：模型请求、批量工具调用、结果回写和继续推理；每次运行有独立的状态与停止原因。
- **工具系统**：本地函数注册、JSON Schema 参数校验、结构化结果、完整调用证据。
- **权限与命令隔离**：工作区路径校验、人工确认、自动执行开关，以及 Windows 原生命令沙箱。
- **模型适配**：执行、摘要和可选模型验收共用适配接口；支持 DeepSeek 和显式配置的 Chat Completions 兼容服务。
- **上下文与会话**：工具结果截断、旧结果清理、历史摘要、会话保存和新会话备份。
- **检查点与恢复**：保存执行位置、模型回复和工具进度，显式续跑；未知执行状态拒绝重放。
- **资源限制**：执行轮数、任务 token 和总时长分别配置；记录服务实际返回的已知用量。
- **可选任务验收**：调用方配置检查程序或模型验收，最多退回一次；默认不额外调用验收模型。
- **离线验证**：本地模拟模型传输、真实文件操作、故障注入及独立的 Windows 沙箱测试。

工具失败会作为结构化结果交回主模型继续判断；通用的失败恢复策略与重复失败干预尚未实现。

## 架构与职责

| 模块 | 职责 |
| --- | --- |
| `agent.py`、`state.py` | 编排执行、管理单次运行事实、记录停止原因；不把本轮结束等同于任务完成 |
| `models.py`、`model_base.py`、`model_openai.py`、`model_deepseek.py` | 创建适配器、处理模型协议与响应，不作工具执行或业务判断 |
| `tools.py` | 工具注册、参数校验、执行及结构化结果 |
| `permissions.py`、`sandbox.py` | 授权、工作区硬规则和命令执行边界 |
| `context.py`、`checkpoint.py` | 管理可压缩聊天历史、会话保存和可恢复的执行现场 |
| `verification.py` | 按调用方给定条件验收，不自行增加任务要求 |
| `limits.py`、`token_usage.py` | 请求前限制检查、单任务额度及进程用量统计 |
| `cli.py`、`prompts.py` | 终端交互、本机配置和执行模型指引 |

通常的执行路径为：输入 → 请求模型 → 校验并授权工具调用 → 执行 → 回写结果 → 再次请求模型。
模型返回普通回答时形成候选；未配置验收器则以 `end_turn` 结束，已配置时按给定条件检查。

模块导入不读取密钥、不创建真实客户端。程序接口可注入模型客户端、工具集、事件接收器和检查点存储；
模型和运行状态模块按源码版本隔离加载，以兼容多版本评测。

## 安装与运行

运行环境为 Windows、Python，以及支持 Windows MXC 的原生 `codex.exe`。
Python 依赖固定在 [requirements.txt](requirements.txt)。本项目只使用 Codex CLI 的本地沙箱子命令，
模型请求由所配置的服务处理。

~~~powershell
git clone https://github.com/eden-alley/harness-evolution.git
Set-Location harness-evolution
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

默认模型为 `deepseek-flash`，地址为 `https://api.deepseek.com`。启动前配置
`DEEPSEEK_API_KEY` 或 `API_KEY`；Windows 进程未继承时，也会尝试读取用户环境注册表中的
`DEEPSEEK_API_KEY`。密钥通过环境配置提供，不写入仓库。

为任务选择独立工作区，然后从仓库目录启动：

~~~powershell
$env:NAMI_WORKSPACE = Join-Path $env:USERPROFILE 'harness-workspace'
New-Item -ItemType Directory -Force -Path $env:NAMI_WORKSPACE | Out-Null
.\.venv\Scripts\python.exe agent.py
~~~

启动后输入任务。实际模型请求会消耗所选服务的 API 额度，工具会真实操作工作区。

| 终端输入 | 行为 |
| --- | --- |
| 普通文本 | 开始新一轮执行，沿用当前会话上下文 |
| `/new` | 先归档检查点、备份旧会话，再清空聊天上下文；保留当前进程 token 累计与权限模式 |
| `/resume` | 显式恢复兼容的未完成检查点，或同步已结束但尚未保存的结果 |
| `/auto` | 查看自动执行状态 |
| `/auto on`、`/auto off` | 开启或关闭已登记工具的免确认模式，默认关闭 |
| `exit`、`quit` | 退出终端 |

`NAMI_WORKSPACE` 默认是启动时的当前目录。未完成检查点存在时，先使用 `/resume` 或 `/new`，
程序不会在启动时自行继续执行。

## 本地 MCP 试点

在项目目录为 MCP 创建独立 Python 环境，再用示例配置启动终端。

~~~powershell
py -3 -m venv .venv-mcp
.\.venv-mcp\Scripts\python.exe -m pip install -r requirements-mcp.txt
$env:NAMI_WORKSPACE = Join-Path $env:USERPROFILE 'harness-mcp-workspace'
New-Item -ItemType Directory -Force -Path $env:NAMI_WORKSPACE | Out-Null
$env:NAMI_MCP_CONFIG = (Resolve-Path .\mcp.example.json).Path
.\.venv-mcp\Scripts\python.exe agent.py
~~~

看到 `mcp__notes__lookup_note` 后，可输入“用 MCP 读取编号 pilot 的示例笔记”。
启动时读取一份本地 stdio 配置。`command: "python"` 指当前解释器，
也可填写本机 .exe 的绝对路径。`args` 中的相对路径以配置文件目录为基准。

`allow_tools` 控制模型可见的工具。`read_only_tools` 是你明确认可可免确认的白名单子集。
其他 MCP 工具逐次确认，`/auto` 开启时也如此。stdio 子进程以宿主账户权限运行，
配置、可执行文件和服务启动脚本应放在任务工作区之外。CLI 会校验配置和可执行文件的位置。
示例只读取固定笔记。

离线验收命令使用真实 stdio 子进程和假模型。

~~~powershell
.\.venv-mcp\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p mcp_stdio_smoke.py -v
~~~

## 远程 MCP

在同一个 `NAMI_MCP_CONFIG` 入口选择远程配置。配置文件用 `url` 指定 HTTPS MCP 端点，
`allow_tools` 决定哪些远程工具进入模型工具表。参数定义从服务发现，调用经过本地校验和权限确认。
更换端点会改变检查点的工具绑定。

~~~powershell
$env:NAMI_WORKSPACE = (Resolve-Path .\playground).Path
$env:NAMI_STATE_DIR = Join-Path $PWD.Path '.mcp-remote-state'
$env:NAMI_MCP_CONFIG = (Resolve-Path .\mcp.remote.example.json).Path
.\.venv-mcp\Scripts\python.exe agent.py
~~~

示例连接公开的 DeepWiki 服务，只开放 `read_wiki_structure`，用于读取公开 GitHub 仓库的文档目录。
输入“用 DeepWiki 查 modelcontextprotocol/python-sdk 的文档目录”，终端会展示发给服务的参数并请求确认。
这一版远程配置适用于公开免鉴权的 Streamable HTTP 端点。远程请求会将已确认的参数发往配置中的服务。

~~~powershell
.\.venv-mcp\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p mcp_http_smoke.py -v
~~~

## 模型配置

`MODEL_PROVIDER=deepseek` 是默认配置。使用其他 Chat Completions 兼容服务时，明确设置：

~~~powershell
$env:MODEL_PROVIDER = 'openai_chat'
$env:MODEL = '<服务支持的模型名>'
$env:BASE_URL = '<服务的 API 基础地址>'
$env:MODEL_API_KEY_ENV = '<存放该服务密钥的环境变量名称>'
.\.venv\Scripts\python.exe agent.py
~~~

`MODEL_API_KEY_ENV` 填环境变量名，密钥放在该变量中。自定义地址不会自动沿用默认 DeepSeek 密钥。
适配层不猜供应商、不自动切换模型、不额外添加重试；保留 SDK 重试及调用方注入的客户端。
兼容服务的工具调用能力需要逐个验证。

当前支持同步文本和原生函数工具调用。流式输出、多模态及其他模型协议不在当前实现范围内。

## 工具、权限与沙箱

内置 `list_dir`、`read_file`、`write_file`、`run_shell`、`fetch_url` 五个工具。
调用顺序固定为参数校验 → 权限检查 → 执行；不会替模型转换参数类型或补造缺失值。

工具返回 `ToolResult`，区分参数错误、工具不可用、用户拒绝、策略拒绝和执行错误。
结果包含成功状态、数据、错误说明，以及适用时的退出码和可用工具列表。
`ok=True` 只表示工具定义的操作成功，整个任务是否完成还需要相应证据。
工具返回非法结果时标记 `invalid_tool_result`；操作可能已经发生，应先核实状态。

- 工作区内目录浏览与文件读取自动允许；写入、命令和网页抓取默认需要确认。
- 写入可以选择本进程内一直允许；拒绝原因会反馈给模型。
- 路径越界、命中危险规则或被策略禁用的工具不会通过人工放行。
- `/auto on` 仅改变确认步骤，硬规则和命令沙箱继续生效；未知风险工具仍需确认。
- 权限检查使用参数快照，回调修改参数会导致拒绝执行。

`run_shell` 固定经过 `codex.exe sandbox` 的 Windows MXC 执行层，使用 cmd 批处理语法。
原生执行器必须位于工作区外；缺失、启动失败或不支持时明确失败，不回退宿主 shell。
单条命令默认 30 秒超时，中断与超时会清理进程树；输出兼容 UTF-8 / GBK。

**隔离边界：** 命令沙箱限制写入，但不是完整的宿主文件读取隔离。子进程筛除 API key 等环境变量，
仍不能由此推断宿主私有文件不可读。`fetch_url` 在宿主进程执行，允许本机和内网可达地址；
它受 URL 协议、重定向次数、I/O 超时和 2 MiB 响应大小限制，不属于命令沙箱的网络隔离。

## 运行状态、会话与恢复

`Agent.run(task, verifier=None)` 返回 `RunResult(text, stop_reason, verification)`。
`RunState` 保存单次运行编号、阶段、执行轮数、调用进度、工具证据、用量与最终结果；
`Agent.messages` 保存聊天上下文。`stopped` 表示运行停止，`end_turn` 表示本轮结束。

默认状态目录为 `~/.nami-agent`，通过 `NAMI_STATE_DIR` 可修改：

- `sessions/default.json`：可截断、清理和摘要的聊天历史。
- `sessions/default.trace.jsonl`：追加的原始执行记录，包括模型响应、完整工具结果、验收和停止原因。
- `checkpoints/default.json`：当前执行快照；归档保留在检查点目录下。

会话和工具结果可能包含用户数据。状态目录应放在任务工作区之外，也不应提交到仓库。

上下文按最近一次执行请求的输入量处理：超过 16000 时清理旧工具结果，超过 24000 时尝试摘要。
近期 3 条工具结果和最近 2 轮用户对话按现有规则保留；工具模型视图最多保留头尾内容，
完整结果另存执行记录。摘要有损且会调用模型；单个过长回合与新增输入仍可能超过模型窗口。

终端默认启用检查点；直接构造 `Agent` 默认不读写检查点。检查点在模型请求及回复保存、
工具执行前后和最终收尾处更新，采用同目录原子替换与 OS 文件锁。保存失败停止后续操作。

恢复遵循以下规则：

- 已保存模型回复和已记录工具结果直接复用，不重复调用。
- 未开始的工具重新检查当前参数与权限；已进入执行窗口但缺结果的工具属于未知状态，禁止重放。
- 轮数、验收次数、任务 token 和首次开始时间不因恢复重置；丢失响应的用量标为未知。
- 源码、工作区、工具、模型或限制配置不匹配时拒绝恢复，不自动迁移。
- 未完成的自定义验收任务暂不支持续跑；当前进程内验收保持可用。
- 检查点恢复程序进度，文件和外部服务不会回滚到旧状态。

`/new` 会保留旧会话备份并归档现场。恢复请求可能产生新的模型用量；未知执行状态需要先核实，
当前版本不自动核实或填造结果。

## 资源限制与 token 统计

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `AGENT_STEP_LIMIT` | `30` | 单次任务执行轮数；`0` 不限 |
| `AGENT_TOKEN_LIMIT` | `0` | 单次任务累计已知 `total_tokens` 上限；`0` 关闭 |
| `AGENT_TIME_LIMIT_SECONDS` | `0` | 自首次开始计算的总时长，可用小数；`0` 关闭 |

在启动窗口设置，重启进程后读取：

~~~powershell
$env:AGENT_STEP_LIMIT = '30'
$env:AGENT_TOKEN_LIMIT = '50000'
$env:AGENT_TIME_LIMIT_SECONDS = '300'
~~~

限制在下一次模型请求前检查，已开始的请求和当前工具批次可以完成，单次调用可能越过阈值。
总时长包括暂停和重启间隔。启用 token 限制而用量缺失或丢失时，以 `usage_unknown` 停止下一请求；
已知用量或时长达到上限时分别为 `token_limit`、`time_limit`。

程序接口用 `max_steps=None` 关闭轮数限制；旧接口 `max_steps=0` 仍表示零轮立即停止。
任务额度与显示的进程累计分开；后者重启归零，`/new` 保留。
对话、摘要和经 `agent.model_adapter` 发出的模型验收各统计一次；缺失字段标为未知，
缓存输入不重复相加，不计算价格。自定义代码直接使用外部客户端的调用不在此统计接口范围内。

## 按任务验收

终端默认不绑定验收器。程序调用方可传入 `verifier(VerificationInput) -> CheckResult`，
优先复用任务已有的测试或检查命令：

~~~python
from verification import command_verifier

result = runtime.run(
    "修复已有测试发现的问题",
    verifier=command_verifier("py -3 -m unittest discover -s tests"),
)
~~~

这里的 `runtime` 是已创建的 Agent 实例。检查命令经过同一套工具、权限和沙箱。

- `pass`：通过给定条件。
- `fail`：退回主模型修正一次，继续使用原轮数；再次失败为 `verification_unmet`。
- `needs_input`：缺少信息或授权，结束本轮等待用户。
- `error`：验收失败或证据不足，明确未完成验证。

也可显式配置 `ModelVerifier(runtime.model_adapter, criteria, runtime.token_usage.record)`，
必须提供明确条件。模型验收只接收本任务证据、不执行工具，其判断仍需要独立评测检验。

## 测试与工程化证据

基础组不需要 API key、真实模型或本机 Codex：

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 tests/run_offline.py
~~~

Windows 原生沙箱组需在具备兼容 `codex.exe` 和 MXC 的主机运行：

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 tests/run_offline.py --native
~~~

基础组使用本地 HTTP 模拟传输，保留 SDK 编解码、真实 Agent 循环、参数校验、权限和文件操作，
并覆盖摘要、用量、协议异常、最终消息一致性、检查点故障及跨进程中断。
原生组验证文件边界、实际读取范围、localhost 网络限制和超时后的子进程清理。
原生组跳过会返回非零退出码，不能当作通过。

本次提交的离线验证记录与源码 SHA-256 绑定，见 [验证记录](docs/validation/2026-11-07.json)。
测试通过说明所覆盖的程序行为符合约定；任务能力改善需要固定模型、任务、环境和评分方式进行版本对照，
保留逐题变化、原始轨迹、工具参数、最终状态和 token。离线测试数量与真实任务通过率分别报告。

BFCL 评测工程和冻结的旧 V0 独立维护，不随本仓库源码同步修改；其外部兼容检查也不等同于模型能力评测。
本次提交未调用真实模型。

## 当前边界与后续取舍

当前主要待完善的是高效检索和分段读取、精确局部修改、失败恢复与重复调用识别。
这些是诊断出的方向，具体行为仍需评审后逐项实现。

多用户服务、异步并发、MCP 接入和完整文件读取隔离尚未实现。工程取舍先明确行为边界与验收标准，
再做小范围改动；每次保留可复现的基线、回归结果、改善与退步。

## 来源

项目起步参考了 [Nami 的 Agent 系列](https://namiai.tech/articles/agent-minimal-loop/)中的循环、
工具、权限和上下文示例。现以独立 harness 项目维护，README 按当前实现组织；
参考来源保留，功能行为以仓库源码及验证证据为准。
