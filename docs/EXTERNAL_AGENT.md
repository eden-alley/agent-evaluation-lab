# 外部 Coding Agent 接入与质量报告交接

本页用于接入和操作。先看当前缺陷及职责划分，请读 [项目现状与取舍](PROJECT_REVIEW.md) → [架构与代码地图](../ARCHITECTURE.md)；全部入口见 [文档目录](README.md)。旧草案相关接口仍保留，自动生成评测题已排除出当前产品方向。

当前能力分析方法为 v0.10.1：程序归档、导入和统计，发起已获授权评测的同一外部 Agent 在同一任务读取固定 Skill、解释关键题并调用程序提交，得到报告和回执后才算交付完成。平台不启动新的分析 Agent 或外部模型，不修改原评分。小范围验证只看指标和关键过程；明确的正式整批评测且超过3题才可附整批建议，建议也可为空。语义分析质量尚未进行模型验证。完整说明见 [COMPARISON_WORKFLOW.md](COMPARISON_WORKFLOW.md)。

## 日常评测与分析接续

在仓库根目录使用项目 Python。先用明确平台地址同步/复用 Skill，保存返回的 `workflow={skill_id,version_id,content_hash}` 到本轮配置；新运行使用当前 catalog 对应正文，旧运行继续保持已固定的方法，不自动升级历史材料。

```powershell
.\.venv\Scripts\python.exe scripts/evaluation.py sync-skill --api-url <明确本机平台地址>
.\.venv\Scripts\python.exe scripts/evaluation.py start --config <假模型验证配置.json> --out <新运行目录>
```

`start --config` 仅用于 `scripted_api`、`validation=true` 的假模型验证，自动冻结配置；验证必须绑定隔离平台与数据目录。真实供应商执行需先 `freeze --config <配置> --out <plan>`，得到本轮明确授权后再 `start --plan <已冻结plan> --approved-plan-sha256 <当轮批准哈希> --out <新目录>`。配置文件或 Skill 本身都不是付费调用授权。真实执行的批准须对应模型、题目、预算硬上限、重试和 Judge 策略；本次实现验证不正式重跑评测。

配置显式提供执行模型、源码和冻结题目，`delivery` 绑定平台与交付信息；具体执行参数以 `scripts/evaluation.py --help` 和 [执行入口](../scripts/README-formal20-concurrent.md) 为准：

新版 Harness 的 `output_policy` 可选 `recovery_max_output_tokens`，与正常 `max_tokens`、`timeout`、`output_truncation_recovery` 一起冻结。未配置则不提高额度。声明更高额度前须确认模型支持；守卫按恢复状态校验实际请求并按该额度预留费用。一次完整恢复后回到正常额度，不能把 `512 → 4096` 的结果当作全程 512 的验证。归档事实显示采用方式及额度，完整响应与原评分仍分开。

| 位置 | 字段与用途 |
| --- | --- |
| 顶层执行配置 | `runtime_entry`, `runtime_entry_sha256`, `source_harness`, `model`, `suite`, `case_ids` 固定入口、源码、模型和题目；`transport`, `validation` 明确真实供应商或假模型验证 |
| `delivery` | `api_url`, `data_root`, `archive_root` 指定平台地址、数据库父目录和归档暂存根目录，不使用隐含日常目的地 |
| `delivery` | `project_id`, `project_name`, `run_id`, `name`, `version` 固定项目、运行身份及版本；新运行使用新目录和新运行编号 |
| `delivery` | `baseline_run_id`, `workflow` 显式选择同一平台上的基线 A，以及固定 Skill 的编号、版本和哈希 |
| `delivery` | `review_scope` 默认 `focused`；明确的正式整批评测选 `formal_batch`，超过3题才允许建议 |

不要在 `delivery` 中以不同值覆盖顶层执行字段，执行与交付记录须保持一致。缺少基线或 workflow 时先报告缺项，不能暗选。没有 A 时必须明确选择只建基线：假模型验证使用 `--baseline-only`，真实供应商执行须在批准前将 `baseline_only=true` 写入冻结计划；不能在执行时改变批准范围，也不能生成升降结论。

执行完整结束后自动归档、导入、统计并准备材料。返回 `analysis_pending` 时，同一发起 Agent 继续以下步骤，不把材料包当作最终交付：

1. 用 `python scripts/evaluation.py continue --run <原运行目录>` 读取原任务状态和 `control_dir`；它按保存状态安全恢复执行或仅继续收尾。
2. 读固定 `Skill正文.md`、`材料摘要.md`、`materials.json` 和必要原件，从退步、异常和建议依据中选择关键题，保留回复区间、具体动作、反馈及转折，填写 `analysis.json`。
3. 用 `python scripts/evaluation.py submit --run <原运行目录> --analysis <分析文件>` 真实提交，核对同一材料包的 `report.json`、`receipt.json` 与 `delivery_complete`。

`analysis_pending` 只表示材料已提供。A/B 分析交付没有 report/receipt 时明确未完成，说明阻塞位置；不新建平台内 Agent，不要求用户另找分析者。显式只建基线时，`baseline_required`、`task_complete=true`、`report_complete=false` 表示基线保存任务完成，未做 A/B 分析，不报告升降或分析报告完成。报告与回执表示程序已接收并校验结构和引用，不证明语义、模型遵循或建议质量。“同一 Agent 接续”是调用方工作约定，程序不独立证明其身份。

只请求分析已有归档时使用 [轻量能力分析入口](CAPABILITY_REVIEW.md)。分析阶段不新增模型调用、重跑、重评或改代码授权；已有执行授权后的本次分析与提交直接接续。恢复、拒收和回执约定见 [真实运行后的归档与报告交付](REAL_RUN_DELIVERY.md)。

## 已有接入

2026-11-12 的逐题对比 MCP 接口继续兼容：`get_comparison_contract`、`list_comparisons`、`create_comparison`、`get_comparison`、`get_comparison_case`、`read_comparison_material`、`submit_comparison_case`、`submit_comparison_report`。当前轻量方法优先一次提交，不要求逐题手工组装请求。

2026-11-12 评分接入已交付。Coding Agent 通过 list_evaluation_runs 发现运行，get_evaluation_run 确认实际案例范围，用 get_skill 固定已发布评分版本，再调用 start_judgment。get_judgment 默认返回概要，指定 case_id 后读取逐项判定与证据引用；get_evaluation_evidence 按行读取清单内原件。当前 archive 与 mock 均为离线模式，模型请求为0。人工终判入口位于网页，本机用户追加理由和决定后保留审计记录。工程依据见 JUDGE_EVIDENCE.md。

本增量依据 2026-11-06 用户纠正与实施授权：用户在外部 Coding Agent 中工作，由它调用平台。用户进一步澄清“不要写 Skill”指具体方法内容必须共同设计；内置 Skill 是平台核心，必须支持按需使用并根据需求生成评测集。本增量实现目录、版本草稿、人工发布、按需发现与产物绑定，不代写任何正式 Skill 方法或业务指令。调用方向替代旧技术设计中的“平台启动 Codex”。既有 Python Agent 注册仍指向被测对象。

## 范围与责任

外部 Agent 通过 MCP stdio 工具读取项目目标、提交不可变用例草案、提交外部质量报告、读取保存的结果。MCP 适配层通过现有 FastAPI 调用业务服务，不直接修改数据库。网页负责审阅报告、拒绝或确认生成固定版本。只新增官方 MCP SDK；不启动付费模型或改动被测 Harness。

平台负责格式/引用/唯一性校验、精确重复检测、报告与内容哈希绑定、持久化和版本确认。外部报告的检查方法由调用方决定，平台不生成质量 Skill 或模型评语。记录声明的客户端与实际引用的已发布 Skill 版本/哈希，不视为经过独立验证的质量保证。

## 内置 Skill 支撑

- 保留“评测集设计”的内置目录项，方法内容为空、状态为待共创，不向工具端伪装为可用 Skill。业务 Skill 由用户按实际业务创建。
- 用户在内置技能页保存亲自提供的内容，形成不可变版本草稿；点击发布后才可由外部 Agent 发现和读取。
- MCP list_skills 可按任务关键词与分类筛选元数据；由外部 Agent 根据适用说明选择，平台不声称关键词匹配等于语义推荐。get_skill 只返回已发布的具体版本。
- 外部 Agent 使用 Skill 生成草案时，source.skills 记录 skill_id、version_id、content_hash；平台校验引用存在且已发布。后续发布新 Skill 版本不改变旧数据集的来源。
- Skill 内容仅作为外部 Agent 可读取的文本，不在平台进程内执行代码。

## 数据合同

- 草案：project_id、name、task_description、requirements[{id,description}]、cases[{case_id,title,input,expected,categories,requirement_ids,grading_notes}]、source{client,skills[{skill_id,version_id,content_hash}]}、base_version_id、request_id。source 兼容可选的 skill_name、skill_version 声明，精确来源以 skills 引用为准。1–500 条案例，1–100 项需求；JSON 请求不超过 2 MiB。案例 ID 唯一且需求引用必须存在。
- 每份草案不可原地编辑；修订提交新草案。同名数据集属于同一项目，确认形成连续版本。已有版本时必须引用当前 base_version_id，过期草案不能覆盖新版本。
- 质量报告：request_id、draft_hash、source、summary、reviewed_case_ids、coverage[{requirement_id,status,case_ids,reason}]、findings[{id,severity,category,case_ids,requirement_ids,evidence,suggestion}]。覆盖矩阵必须覆盖每项需求；引用只能来自本草案；声明已覆盖的用例必须已检查且关联该需求。
- 报告追加保存，不能覆盖旧报告。发布必须指定当前最新报告 ID，检查覆盖完整、无阻断项；警告或覆盖不足必须填写接受说明。发布生成内容与报告快照，不接受后续报告覆盖。
- MCP 不提供审批工具。网页审批属于本机单人工作流，不是能对抗同用户任意本地代码的权限隔离。

## 对外工具

get_platform_status、list_projects、get_project_context、list_skills、get_skill、get_submission_contract、list_dataset_drafts、submit_dataset_draft、get_dataset_draft、get_quality_report、submit_quality_report、list_dataset_versions、get_dataset_version。

工具返回真实服务器对象或明确错误。设置页显示可复制的启动配置、提交数据合同以及最近实际工具请求时间；不将“服务可用”表述为“外部客户端已连接”。

## 验收

本地独立 MCP 客户端完成工具发现、读取数据合同、提交草案、质量报告读取；网页能定位案例/需求证据、确认版本。自动测试使用独立数据库与明确标注的测试夹具。外部模型的质量判断能力需后续真实任务验证，本增量不声称已证明。
