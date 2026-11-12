# Agent Evaluation Lab

本地 Agent 评测工作台。用户在外部 Coding Agent 中工作，按需使用平台中已发布的 Skill，生成评测集草案和质量报告；平台负责校验、证据保存、人工审阅与版本确认。

## 当前可用

| 能力 | 实际状态 |
| --- | --- |
| 外部 Coding Agent 接入 | 官方 MCP stdio 工具，通过本地 API 读写平台；已用独立协议客户端验证 |
| 项目与被测 Agent | 项目持久化、配置登记、路径静态检查 |
| 内置 Skill | 目录、分类筛选、用户内容草稿、人工发布、不可变版本、按需读取 |
| 共创 Skill 方法 | 已收录通用 Harness 评测 v0.1.2、结果判定与评分 v0.1.0；首版试用，原始包与平台导入内容见 [skills](skills/README.md) |
| 业务 Skill | 用户可创建目录项并提供内容；平台不代写业务方法 |
| 数据集质量交接 | 不可变草案、程序校验、外部报告、覆盖数、案例证据定位、人工确认固定版本 |
| 真实运行与证据展示 | 读取外部运行归档，展示逐项判定、原题面、轨迹和交付文件；见 [归档说明](docs/EXTERNAL_RUN_IMPORT.md) |
| 评测执行与运行比较 | 外部 Harness 执行；平台内执行器待接入，运行比较页保留明确标记的示例 |

平台不执行 Skill 文本、不调用模型生成用例。生成与语义检查由外部 Coding Agent 按用户要求完成；平台不会将外部报告自动认证为质量保证。

仓库保存可迁移的 Skill 文件；发布状态保存在本机数据库中。克隆后的实例须按 [Skill 同步说明](skills/README.md) 导入并经用户授权发布。原有 `dataset-design` 内置占位项仍未发布，不与已发布的“通用 Harness 评测”混为同一目录项。

## 本机启动

需要 Node.js 22+、Python 3.11+。本轮使用 Windows、Node 24、Python 3.14 验证。首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
cd apps/web
npm ci
npm run build
cd ../..
```

启动：`powershell -ExecutionPolicy Bypass -File ./start.ps1`。
停止：`powershell -ExecutionPolicy Bypass -File ./stop.ps1`。

- 工作区：http://127.0.0.1:3100/projects
- 内置技能：http://127.0.0.1:3100/skills
- 数据集：http://127.0.0.1:3100/datasets
- 外部接入：http://127.0.0.1:3100/settings

数据库为 `data/lab.sqlite3`；迁移自动保留已有项目和配置。启动日志在 `data/runtime`。SQLite 使用 WAL。Ubuntu 及现有 Harness 的 Linux 兼容性尚未验证。

## 从外部 Coding Agent 使用

1. 在网页创建项目，填写用户需求与评测目标。
2. 共同设计 Skill 内容，在“内置技能”保存草稿并人工发布。没有发布版本时，外部工具不会将其列为可用能力。
3. 在“设置”复制 MCP 启动字段，在外部客户端添加本地 stdio 服务。MCP 进程由客户端启动；平台 API 必须已启动。
4. 外部 Agent 调用 `list_projects`、`get_project_context`，再通过 `list_skills` / `get_skill` 按需读取已发布方法。关键词筛选不是语义推荐，是否适用由 Agent 和用户判断。
5. 调用 `get_submission_contract` 取得 JSON Schema，提交 `submit_dataset_draft`；生成来源以 `source.skills` 绑定已发布技能版本与哈希。
6. 外部 Agent 提交 `submit_quality_report`；用户在网页查看检查数量、覆盖矩阵、问题与原文引用，确认或退回。

Codex CLI 的接入命令（已核对本机 `codex mcp add --help`；这里不自动修改客户端全局配置）：

```powershell
$labRoot = (Get-Location).Path
codex mcp add agent-evaluation-lab --env LAB_API_URL=http://127.0.0.1:8100 --env LAB_CLIENT_NAME=codex -- "$labRoot\.venv\Scripts\python.exe" "$labRoot\backend\run_mcp.py"
```

从本项目根目录运行，再按客户端要求重新加载 MCP 服务。其他客户端使用设置页的 `command`、`args`、`env` 字段。不会将模型凭据保存在平台配置中。

MCP 只提供读取、草案和报告提交工具，不提供发布技能或确认数据集的工具。网页审阅是本机单人工作流，不是能阻止同用户任意本地脚本访问 HTTP API 的安全隔离。

## 文件责任与数据流

| 文件或目录 | 责任 |
| --- | --- |
| `backend/lab/mcp_server.py`、`backend/run_mcp.py` | 标准 MCP 工具适配，通过 HTTP 调用业务接口 |
| `backend/lab/integration.py` | 接入配置、项目上下文、实际工具请求记录 |
| `backend/lab/skills.py` | 用户提供的技能内容、发布状态和版本引用 |
| `backend/lab/quality_schemas.py` | 草案、来源、报告、证据与审阅合同 |
| `backend/lab/quality_checks.py` | 确定性校验、规范化哈希、引用片段验证 |
| `backend/lab/datasets.py`、`quality_routes.py` | 草案/报告存储、原子确认与不可变版本 |
| `backend/lab/migrations` | 按版本迁移 SQLite，保留旧数据 |
| `backend/lab/evaluation_imports.py`、`evaluation_trace.py` | 读取归档运行和清单内证据，核对路径与哈希并整理可回查的轨迹 |
| `apps/web/components/connections.tsx`、`skills.tsx` | 接入与技能界面 |
| `apps/web/components/dataset-workspace.tsx`、`quality-detail.tsx` | 项目隔离、报告审阅、案例证据与固定版本 |
| `apps/web/lib/quality-api.ts`、`quality-types.ts` | 前端请求与数据合同 |

外部 Agent → MCP stdio → FastAPI → SQLite。浏览器 → Next.js 同源转发 → 同一 FastAPI。MCP 不直接写数据库。程序校验与外部语义判断分开显示；来源哈希只证明引用对应版本，不证明实际执行遵循了方法。

新增 `mcp==2.3.0` 使用[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)实现协议与客户端验证；`httpx` 用于本地桥接。传递依赖已写入 `backend/requirements-lock.txt`。没有新增模型 SDK 或分布式组件。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q --basetemp ../test-temp
cd ../apps/web
npm test
npm run typecheck
npm run build
```

完整结果见 `VERIFICATION.md`。浏览器验收脚本为 `tests/ui_quality_smoke.py`；必须对独立测试服务运行，配置 `LAB_TEST_WORKDIR`（临时产物目录）、`LAB_UI_API_URL`、`LAB_UI_BASE_URL`，不得指向真实工作区。脚本会创建明确标注的测试项目和测试内容。
