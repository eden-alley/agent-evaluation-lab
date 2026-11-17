# 真实并发执行、异常恢复与报告交付 Implementation Plan

> **执行状态：** 用户已于 2026-11-16 授权实现及假模型真实路径集成验证；禁止真实模型、正式评测、历史覆盖与 GitHub 推送。进度与证据见 `work/real-delivery/progress.md`。

**Goal:** 将真实单题执行接入可配置并发，并把归档、指标升降、关键题讲解及正式批次建议接到同一条可恢复的交付链。

**Architecture:** 继续由外部执行器运行任务，平台接收归档和分析。复用现有协调器、原 Agent/工具/检查点/评分代码、轻量 Skill 和报告接口；补齐真实运行适配与收尾调用，不新增平台内执行 Agent 或分析服务。

**Tech Stack:** Windows、Python 3.11+、现有 SDK 兼容接口、标准库进程/Pipe、现有 FastAPI/SQLite/Next.js；复用项目依赖。

**Spec:** 本轮用户要求及本文设计约定；承接 [上一版并发计划](2026-11-15-concurrent-formal20-runner.md)，新增的验收标准取代“只有合成任务通过即可宣布主链完成”的口径。

## Global Constraints

- 本轮实现本计划，在隔离副本使用假 API、真实 Agent/工具/原评分器进行集成验证；不调用真实模型、不重跑正式评测、不覆盖历史、不提交或推送 GitHub。
- 后续集成验证必须用真实生产代码路径，模型 API 使用固定响应替身；不得再以 `SIM-*` 或 `synthetic_entry.py` 作为主链验收。
- 历史运行、原评分规则/源码、原题、被测 Harness 和旧入口保持原字节；不覆盖原 `grade.json`、复核或报告。
- 未来的验证只在临时任务副本、临时运行目录、隔离数据库/项目中执行，明确标为“假模型集成验证”；不启动正式20题实跑，不作为模型能力分数，不写日常项目。
- **评分边界明确：** 完整单题路径末尾会调用原 `grade_case`。未来集成测试若要证明这段接通，必须在临时产物上调用未修改的评分代码，不能假造 pass；本计划阶段不执行。若某环境不允许运行该段，应记为未验证，不能声称全链路通过。
- 并发数为正整数，验证覆盖 1、2、4、8；统一预算、请求上限和全局限流不随进程数放大，单题内保持顺序。
- 默认不重试 API；任何真实运行及重试策略必须冻结到新执行计划并获得该轮授权，旧批准不沿用。
- 1～3题只交付指标与关键过程；明确 `formal_batch` 且超过3题时才可附整批开发建议。有据才给，允许零建议，不要求无建议理由。
- 复用 v0.9 轻量 Skill 与当前 `ReviewSubmission/Analysis`，不新增评分逻辑、跨维度总分或强制全量20题讲解。
- 不修改日常平台数据库或历史报告；计划中的新接口与页面测试均在隔离实例验证。

## 已确认的缺口

1. `scripts/formal20_concurrent.py` 只有 `simulate`；`formal20_worker.py:run_legacy_probe` 只允许合成入口。已有调度测试不能证明真实任务可并发。
2. 真入口在评测工作目录 `outputs/harness-v0.40-formal20-20261115/work/run-formal-current.py`。旧 `execute_case` 包含工作区、Agent、工具、阶段产物并在末尾调用 `grade_case`；旧 RequestGuard 无锁读改同一预算文件，不能原样放进多个进程。
3. 新 worker 的手写检查点不是原生 `CheckpointStore` 格式；恢复后的本地 attempt 重新从1计数，会与旧许可的幂等键冲突。
4. 旧单题执行器与新调度器都写 `<run>/<case>/result.json`，直接接入会覆盖执行证据。
5. 最新真实批次已导入，但没有对应 comparison。现有 prepare 才计算指标，submit 才将指标写入报告；页面无报告时不显示指标。
6. 准备分析默认可能取当前活跃 Skill；重复准备还会产生新 delivery。收尾恢复不能依靠“重新 prepare 一次”代替同一次提交恢复。

旧真实入口、原题和冻结源码均位于 `C:/Users/叶宸玮/Documents/Codex/2026-11-06/new-chat-5`，由明确路径及指纹绑定；禁止依靠搜索“最新目录”选择它们。

## 完成后的闭环

```text
冻结任务/模型/预算/基线/Skill/用途
  → 真实单题代码并发执行
  → 原评分及证据归档、导入
  → 自动创建对比并保存指标
  → 提供固定 Skill 与关键题材料
  → 外部 Agent 分析并提交
  → 平台返回回执，显示表格、讲解及有据建议
```

| 阶段 | 责任方 | 必须留下的产物 |
| --- | --- | --- |
| 执行与恢复 | 外部执行器 | 每题 workspace、原事件/消息/阶段/结果/评分、请求账本、执行状态 |
| 导入与统计 | 收尾程序＋现有平台接口 | manifest、导入回执、comparison_id、固定指标表及可比范围 |
| 材料提供 | 程序 | 固定 Skill 正文/版本/哈希、packet、用途、关键题候选、证据目录 |
| 关键分析 | 发起本次任务的外部 Agent | 按回复区间解释的关键题；正式批次可有最多3条有据建议 |
| 提交与展示 | 程序＋平台 | request、report/receipt、页面链接、实际讲解覆盖和分析状态 |

**外部 Agent 仍承担语义分析。** 执行器不会自动编造讲解，也不默认启动 Codex CLI 或付费 Judge。运行命令返回时若分析尚未提交，必须返回待办材料和 `analysis_pending`，发起任务的外部 Agent 应继续读取 Skill、分析、提交，取得回执后才能宣布“交付完成”。无人接续时，平台真实显示待分析，不能把导入成功当作报告完成。

## 设计约定

### A. 真实执行与唯一假边界

- 保留 `simulate` 回归入口，新增 `execute --transport scripted_api --validation --plan <配置> --out <新目录>`；真实传输为 `execute --transport provider_api --plan <配置> --approved-plan-sha256 <新指纹> --out <新目录>`，未获当轮授权不可启动后者。`resume --run <已有目录> --plan <原配置>` 使用相同传输与绑定，不能借恢复切换模型、预算或校验规则。
- 冻结配置至少包含 suite/source/evaluator 路径与指纹、runtime版本、模型参数、workers、在途上限、全局间隔、总/单题次数、费用预留、超时、重试策略、基线、Skill和用途；实际 worker 不从各自环境重新选择这些值。
- 将旧单题执行调度迁入项目内的 `scripts/formal20_runtime.py:execute_case`，只参数化路径、请求代理与检查点策略；原 Agent、CaseAdapter、响应规范化、工具执行、权限和评分仍复用冻结代码。历史脚本不回写，新入口的真实运行和验证均调用同一个函数。
- 不以测试专用函数替代 `execute_case`、`Agent.run/resume`、`ToolRunner.handle_call`、`MXC.run_command` 或 `grade_case`。可用记录调用的探针，但必须执行原函数体。
- **模型的唯一替换点是 `client.chat.completions.create(**payload)`**：返回 SDK 兼容响应或指定异常。FakeModel 不直接写 workspace、不执行工具、不伪造工具结果或评分；所有动作必须由真实 Agent 解析后经过原工具入口。
- 同时保留两个传输工厂：`scripted_api` 无凭据，供集成验证；`provider_api` 仅在新的冻结计划和该轮授权有效时开放。两者共用执行代码，禁止固定响应耗尽后回退真实 API。
- 验证环境允许读取指纹绑定的真实依赖，禁止外网和 paid_client 构造；只按测试需要允许绑定的 loopback 服务。当前一刀切拒绝读取旧源码/所有 socket 的 OfflineBoundary 不能直接沿用。
- fake worker 启动前过滤敏感环境变量名，启动后在加载真实依赖前清理残留敏感变量，不读取或记录其值；MXC 的环境遍历必须在清理后的环境执行。不能通过 mock 原生 `run_command` 绕过这个问题。
- 真实工具命令仍在原生 Windows 沙箱执行；运行目录保留在既有评测 outputs 隔离范围内。沙箱不可用就记环境阻塞，不能换宿主 shell 或返回虚构成功。

### B. 预算、异常和恢复

- 只有 Coordinator 修改全局账本；worker 的生产 RequestGuard 做原模型/参数/usage/响应检查，通过 Pipe 申请、结算，不直接写共享预算。
- 保留原费用预留公式；发许可前预留落盘，已结算估算＋所有未结算预留＋新预留不得超过上限。网络等待不阻塞记账循环。
- 增加可回放的 `request-ledger.jsonl` 作为记账事实，`budget.json` 是原子快照；记录请求许可、SDK原始响应、结算、未知用量及停止。响应先持久化，再通知消费；不从一个空账本恢复旧批次。
- 请求包含稳定 `logical_request_id`、物理 `attempt_id` 和全局请求序号。逻辑身份绑定 case/轮次/原生检查点位置及持久序号，不能只用 payload 哈希，也不能在新进程从1重置。重试是新的物理请求、累计次数和预留。
- 已保存响应但 Agent 尚未消费时，恢复应通过同一响应解析代码重放保存响应，不再次调用 SDK；已 recorded 的工具调用由原生 resume 跳过。
- API 异常默认停批；若计划显式允许临时异常重试，第一版只支持0或1次，保存异常类型、HTTP状态、供应商request ID、Retry-After和脱敏摘要。未知费用预留不释放，不能凭“后来成功”推定前次免费。不记录密钥、Authorization 或完整敏感错误正文。
- 全局停止后不再发新请求、新题或恢复任务；已经许可的请求在原超时内排空并记账。排队等待不算请求超时；length 截断、429、连接失败、评分故障分别记录，不能统一叫 Agent 失败。
- 每题使用原生 CheckpointStore；仅在绑定一致、状态可恢复、账本已对齐时调用原 `inspect_checkpoint/resume`。保留原生拒绝规则，特别是 executing 工具状态和自定义 verifier 的恢复限制。
- O08 用真实 `arm_interruption → CheckpointStore.save → recorded → 86 → Agent.resume`，不使用手写 checkpoint.json。恢复仍占原逻辑槽位、使用同一工作区、累计预算。
- 对没有可信检查点、半截账本尾记录、绑定漂移或副作用无法确认的现场，返回 `needs_recovery` 及原因，保留证据；不自动重做、不靠手改 budget.halt 或临时续跑脚本继续。
- 父进程的执行状态写 `execution-state.json`/`worker-state.json`，不得覆盖旧单题 `result.json`、`phases.json` 和 `grade/`。中断重入不覆盖已完成题目录。

### C. 导入后的统计与报告

- 启动配置固定 `baseline_run_id`、本批 run_id、case_ids、Skill精确版本和 review_scope。缺基线时允许保存执行归档，但标明 `baseline_required`，不能生成虚假的升降。
- 新 `formal20_archive.py` 提取原导入合同的通用导出/manifest校验/原子发布逻辑，不能继续硬编码某批309次请求或具体旧目录。只读汇入原 grade/复核，保留 unknown、invalid、未运行、未知费用。
- `formal20_pipeline.py` 在归档校验后调用现有 `POST /comparisons`。创建请求正文和确定性 request_id 先落盘；重复收尾取回同一 comparison，不重复执行任务、评分或导入。
- 创建新 comparison 时计算并将机器统计保存在不可变 snapshot：`metric_report`、比较条件、指标/过程判据版本及哈希。无需新建报告类型或数据库表；旧 comparison 不在 GET 时补写或重算。
- 统计和语义报告分开。无分析报告时先显示已保存指标；不能自动提交空 Analysis 来凑出表格或制造“已分析”。历史报告仍显示该报告自己的统计口径。
- `review.prepare` 与 packet_hash 使用所固定的统计版本和 Skill，不因当前 metrics.VERSION 或活跃 Skill 升级而变。新收尾流程必须显式传固定版本，旧接口行为保留兼容。
- 复用现有 CLI 文件准备/提交及 ReviewSubmission，固定 `packet.json`、Skill正文、delivery_id、analysis.json、request.json、receipt.json。恢复优先复用原文件；超时不换 request_id、不自动再次 prepare，真实冲突才明确开启新一轮。
- 关键题按退步、异常及建议依据选择；建议引用题和明确指定题必须讲解。讲解含背景、回复区间、实际动作、反馈、转折与验收，逐段引用原件。
- 正式批次有建议时必须包含问题、优先理由、具体动作、验证办法和支撑题；可以零建议。不得以建议数量、全20题讲解或“Skill已提供”作为报告质量/阅读证据。
- 收尾状态放在独立控制目录，禁止向已经冻结的 manifest 内追加文件：`execution_complete → archive_imported → statistics_ready → analysis_pending → report_received`，另记录错误与最后成功阶段。`delivery_complete` 仅在有效报告回执可核对后成立；报告质量未校准须继续明确。

### D. 平台呈现

- 评测页能进入该 run 的关联对比；有多份对比则列出，不擅自把时间最新者当成唯一基线。
- 对比页在外部分析提交前即显示指标及“等待分析提交”；已提供 Skill 只表示材料已提供，不显示成“Agent正在分析”。
- 报告收到后，复用现有表格、逐题过程和正式建议区；建议为空不显示空建议块。详情页继续投影最新相关报告中的讲解，不复活历史缺席内容。
- 保留“执行完成”和“报告交付完成”两个事实，不再用单一完成字样覆盖整个流程。

## 实施文件范围

| 范围 | 文件及职责 |
| --- | --- |
| 修改执行器 | `scripts/formal20_concurrent.py`（真实后端/恢复/结束收尾）、`formal20_coordinator.py`（持久记账/异常详情）、`formal20_worker.py`（生产worker、原生恢复、隔离环境） |
| 新增运行适配 | `scripts/formal20_runtime.py`（从旧入口迁移单题调度，委托原 Agent/工具/评分） |
| 新增收尾 | `scripts/formal20_archive.py`（通用归档导入）、`formal20_pipeline.py`（可重入收尾与外部分析待办） |
| 复用分析文件流程 | `scripts/capability_review.py`（可调用的准备/原请求提交及恢复），不另造报告协议 |
| 平台统计 | `backend/lab/comparisons/service.py`、`review.py`、`metrics.py`（固定机器统计及条件、返回状态、固定版本身份） |
| 页面接线 | `backend/lab/evaluation_imports.py`（只读关联对比）；`apps/web/lib/comparisons.ts`、`components/comparison-report.tsx`、`comparison-workspace.tsx`、`evaluations.tsx`（表格回退、状态与入口） |
| 文档 | `scripts/README-formal20-concurrent.md`、`docs/CAPABILITY_REVIEW.md`（更新真实路径与外部分析责任，不扩大 Skill） |
| 新增测试 | `scripts/tests/test_formal20_real_path.py`、`test_formal20_recovery.py`；`backend/tests/test_run_delivery.py`；`apps/web/tests/run-delivery.test.ts` |

原 `review_schemas.py`、`delivery.py`、评分器和 Skill 正文原则上不改；若实施发现需要改接口，先在实施记录说明具体原因，不扩展评分或分析字段。

## Review Focus

1. 假模型开关存在但执行仍走简化 worker，或底层偷偷回退真实API：任务1/6必须以真实调用轨迹和外网/paid_client哨兵证明没有。
2. API响应已保存未消费、工具已经执行未记账、恢复后请求序号复用：任务2分别验证重放、拒绝及累计记账。
3. 归档导入后崩溃、提交响应丢失、prepare生成新delivery：任务3/4验证逐阶段重入，不能重跑任务或重复报告。
4. 新旧统计版本、Skill版本、原件和旧报告串用：任务3/5验证固定身份、原件漂移及历史页面不变。
5. 无报告先出指标、关键题遗漏、有/无建议、小批次误挂建议：任务4/5验证实际提交约束与页面状态，不只检查HTTP200。

---

## Task 1：把真实单题执行接入并发worker

**Interfaces:** `execute_case(config, case, run_dir, client)`；`client` 由 `scripted_api/provider_api` 工厂注入，生产与验证共用同一函数。

- [ ] 先写 `test_real_case_path_uses_original_agent_tools_and_grader`，用临时 U05 真实冻结副本；断言执行真实函数、产生真实事件/工具反馈/评分，替换 execute_case、MXC 或 grade_case 返回固定结果时测试应失败。
- [ ] 实现项目内运行适配与环境边界，冻结依赖指纹；把模型校验、预算代理、归档路径接入生产代码，不依赖测试里临时替换类来绕过记账。
- [ ] 补 `test_fake_transport_never_falls_back_to_provider`、`test_native_sandbox_failure_is_not_success`、`test_result_and_worker_state_do_not_overwrite_each_other`。
- [ ] 运行 `python -B -m unittest discover -s scripts/tests -p test_formal20_real_path.py -v`，先确认RED，再实现GREEN；原评分源指纹必须不变。

## Task 2：统一真实异常、账本恢复和原生检查点

**Interfaces:** `inspect_run(run_dir)` 返回可继续/需要恢复/拒绝及依据；`resume_run(plan, run_dir)` 先验证冻结绑定和账本，再处理原生可恢复任务；不新建预算。

- [ ] 先写 `test_response_durable_before_consume_is_replayed_once`、`test_resume_request_ids_do_not_restart`：在真实响应解析和检查点边界注入进程中断，恢复不重复SDK请求、计费或消费。
- [ ] 写 `test_real_recorded_checkpoint_skips_receipt_write`：真实 O08 代码路径触发86后恢复，核对 native run_id、messages/call_records、mtime及真实工具调用次数，不以合成 receipt_writes 字段作为证明。
- [ ] 写 `test_executing_tool_or_binding_change_refuses_resume`、`test_verifier_recovery_limit_is_explicit`、`test_partial_ledger_stops_recovery`。
- [ ] 写连接异常/429/length/无usage及已保存响应的对照用例，验证脱敏元数据、默认零重试、可配置一次重试的预算累计，以及停批后排空。
- [ ] 实现后运行 `python -B -m unittest discover -s scripts/tests -p test_formal20_recovery.py -v`，通过后保留程序测试回执，不产生正式成绩。

## Task 3：归档后自动创建对比，独立保存机器统计

**Interfaces:** `finalize_run(config, run_dir, api_client)` 返回导入/对比/统计身份及下一动作；`resume_delivery(control_dir, api_client)` 只恢复未完成收尾阶段。

- [ ] 先写 `test_imported_run_gets_comparison_and_statistics_without_analysis`，走真实导出/manifest/导入合同和 POST /comparisons；指标落盘且页面读取不依赖分析报告。
- [ ] 写 `test_finalize_is_idempotent_at_each_crash_boundary`：每个阶段之后中断并重入，同一run/manifest/请求不重复发布、创建或重评；缺基线显示 baseline_required。
- [ ] 提取通用归档与收尾代码，固定统计快照、比较条件、版本及哈希；新流程不直接调用某批临时 import_final.py，旧入口及归档原样保留。
- [ ] 写 `test_statistics_and_packet_use_frozen_registry`、`test_history_is_not_recomputed_on_get`，升级运行时代码后新旧报告仍各用自己的表。

## Task 4：把外部分析待办与提交接到收尾

**Interfaces:** `prepare_analysis_task(control_dir, comparison_id)` 保存固定包及待办；`submit_analysis_task(control_dir, analysis_path)` 使用原 request 幂等提交并保存可核对回执。

- [ ] 先写 `test_fixed_skill_and_key_case_materials_are_delivered`：实际读取固定Skill正文/哈希、关键题候选和原件；不只验证版本号或复制旧范例。
- [ ] 写 `test_report_receipt_required_for_delivery_complete`：只有统计、只有提供Skill、只生成本地analysis都不能标交付完成；有效 ReviewSubmission 回执后才完成。
- [ ] 写 `test_lost_submission_response_reuses_original_request`：服务端已提交但客户端未收到时，用原包和request取回同一报告；不重复prepare或切换Skill。原件变化/STALE_REVIEW保留冲突，不自动改新稿。
- [ ] 正式批次分别测试“有依据建议”与“零建议”，focused/最多3题禁止建议；明确讲解题及建议引用题缺讲解或证据则真实接口拒绝。
- [ ] 固定分析文档仅作为假分析者的响应输入，仍真实走材料读取、Schema、引用校验、事务提交和回执；不直接写数据库或伪造报告对象。这不证明真实模型遵循Skill或分析质量。

## Task 5：平台展示准确的流程状态

**Interfaces:** 对比详情新增固定机器统计及派生分析状态；评测页返回关联对比入口，均通过现有只读查询派生，不增加后台队列。

- [ ] 先写 `test_statistics_visible_before_report`、`test_report_keeps_its_own_metric_version`：新对比无报告先显示表，选旧报告不混入当前表。
- [ ] 写 `test_run_links_pending_and_received_analysis`：能从本批进入对应对比；无分析显示待提交，有回执显示已收到，并保留实际讲解覆盖。
- [ ] 保留 `run_explanations.py` 回归：最新相关报告未讲某题时不自动复活旧讲解；无建议时无空建议区。
- [ ] 运行目标后端测试、`npm test` 和 `npm run typecheck`；若修改页面结构，再在隔离实例实际打开详情/对比并核对显示内容，不把构建成功代替页面验收。

## Task 6：真实路径集成验证与交付

**验证材料：** 使用 U01、U02、U04、U05、C02、C03、C04、C05 的真实冻结任务副本作为并发选集，不用 SIM 题名或改成构造题；另用 O05/O06/O07/O08 的真实路径定向检查服务、验收、压缩及恢复协议。此为程序集成测试，不重新发布正式20题成绩。

- [ ] 在1、2、4、8档运行同一真实路径选集，只有 SDK 响应用脚本控制；核对真实PID、调用轨迹、原工具副作用、原评分文件、账本与完整归档。正常/故障分开验证；8题槽＋2在途单独验证。
- [ ] 对 O05 允许所绑定的真实 loopback 服务，其他网络仍禁；O06 真实 verifier、O07 真实压缩分支、O08 原生检查点均不得mock。原评分已知无效项保持无效，不为了GREEN调整口径。
- [ ] 完整接通一次 `真实U05副本 → 假API响应 → 真Agent/工具/原评分 → 真导出导入 → 真comparison/统计 → 固定分析响应 → 真提交 → 真页面读取`。A/B都来自隔离验证运行，假模型结果明确标注，不宣传模型能力改善。
- [ ] 另只读重放现有真实A/B归档的副本，验证当前20题指标及关键题引用可进入同一收尾流程；不重新调用其模型或重算既有评分。明确区分历史请求数量与本次新增调用数。
- [ ] 所有测试使用隔离数据库/端口/项目；comparison analyst 为 offline_fixture，页面与记录明确标为集成验证，不进入日常真实运行列表。validation 模式必须显式提供测试 app/client 或隔离平台地址及数据目录，缺少时拒绝收尾，不能回退日常8100服务；只允许绑定测试服务和O05端口，不开放所有本机服务。
- [ ] 后端建议命令：`python -B -m pytest backend/tests/test_run_delivery.py backend/tests/test_capability_review.py backend/tests/test_run_explanations.py backend/tests/test_comparison_task_identity.py -q --basetemp <新的测试目录>`；scripts 测试依任务1/2命令运行。测试环境注入真实API/凭据访问哨兵，任何漏出即失败。
- [ ] 交付按“已接通/已验证/未验证”列出的报告，附阶段回执、指标表、关键题页面、建议有/无两个展示及重入证据；不能只报测试数量和HTTP200。

## 最终完成标准

真实运行入口不再只接受 synthetic；它与假模型验证使用同一条执行代码。异常恢复不重置账本、不重复已记录副作用，无法安全恢复时明确拒绝。跑后无需临时补脚本即可保存指标并提供分析材料，外部Agent交付后平台能展示关键经过和有据建议。

阶段完成必须附：真实路径函数/模块绑定、假API边界证据、原评分未变指纹、过程/归档/对比/提交/页面回执。任何一段只是占位或mock，均单列未完成。零真实模型调用与隔离测试通过不等于正式模型效果、供应商配额或实际并发提速已验证。

**当前状态：仅计划已保存；全部实施与验证步骤均未执行。**
