# 外部 Agent 版本对比 workflow

本页记录当前操作及历史接口兼容，不是新的架构方案。先理解项目请读 [项目现状与取舍](PROJECT_REVIEW.md) → [架构与代码地图](../ARCHITECTURE.md)；按需查阅见 [文档目录](README.md)。

当前默认方法为轻量能力分析 v0.10.1，正文见 `skills/agent-version-comparison-workflow/SKILL.md`。程序全量统计并提供关键题候选；发起已获授权评测的同一外部 Agent 在同一任务接续读取固定 Skill，讲解退步、异常和建议依据中的关键题，再调用程序真实提交。`analysis_pending` 只是材料已备好，收到对应报告和回执、状态达到 `delivery_complete` 才能宣布报告交付完成。

小范围验证只输出指标和关键过程；默认用途 `focused`，明确的正式整批评测使用 `formal_batch` 且超过3题才允许建议，也可省略或为空，不要求原因。关键题保留具体回复区间、动作、实际反馈和关键转折，不把讲解压成几句泛化总结。选题、字段和引用见 [方法正文、提供记录与输出检查](CAPABILITY_REVIEW.md)。

## 日常入口

配置、平台目的地、A 基线和 workflow 均须明确，不能从历史运行或活跃 Skill 中暗选。先用 `sync-skill` 取得本版固定 `workflow` 三字段并存入配置；命令追加或复用相同内容版本、保留旧版本和旧报告。新运行核对当前 catalog，旧 `continue` 仍用原方法。

```powershell
.\.venv\Scripts\python.exe scripts/evaluation.py sync-skill --api-url <明确本机平台地址>
.\.venv\Scripts\python.exe scripts/evaluation.py start --config <假模型验证配置.json> --out <新运行目录>
.\.venv\Scripts\python.exe scripts/evaluation.py continue --run <原运行目录>
# 同一 Agent 读取返回 control_dir 内的 Skill正文.md 和材料，写 analysis.json。
.\.venv\Scripts\python.exe scripts/evaluation.py submit --run <原运行目录> --analysis <分析文件.json>
```

`start --config` 仅允许 `scripted_api`、`validation=true`，不是付费调用授权。真实供应商执行先 `freeze --config <配置> --out <plan>`，得到本轮明确批准后再使用 `start --plan <已批准plan> --approved-plan-sha256 <当轮批准哈希> --out <新目录>`。没有 A 时须明确只建基线：假模型验证使用 `--baseline-only`，真实供应商执行须在批准前将 `baseline_only=true` 写入冻结计划；不输出升降。完整配置及授权边界见 [外部 Agent 接入](EXTERNAL_AGENT.md#日常评测与分析接续)。

程序完成执行后，自动归档、导入、生成机器统计并提供固定材料；同一外部 Agent 随即完成分析与提交，不提前结束或只把材料交给用户。平台不新建分析 Agent，不自动启动外部模型。分析属于已有授权评测的本次交付；只有归档分析请求时，不新增执行、重跑、重评或修改代码授权。原评分和历史报告保持原样。

| 状态 | 含义及下一步 |
| --- | --- |
| `baseline_required` | 显式只建基线时，`task_complete=true`、`report_complete=false` 表示基线保存完成，未做 A/B 分析，不能判断升降 |
| `analysis_pending` | 固定 Skill、统计和分析模板已准备；同一 Agent 继续读原件、写分析并提交 |
| `report_received` | 报告已返回，仍需保存并核对回执 |
| `delivery_complete` | 对应 `report.json` 与 `receipt.json` 已保存；结构和引用通过，语义质量未校准 |

控制目录位于执行目录和不可变归档之外，按返回的 `control_dir` 定位。`continue` 读取同一次任务状态，安全恢复已有执行或只复用未完成收尾；已有 comparison、packet 与请求不另造。超时恢复原请求，明确422拒收与409冲突按 [恢复约定](REAL_RUN_DELIVERY.md#恢复) 处理，不能篡改已绑定分析来伪装重试。A/B 分析交付缺原包、基线或回执时明确阻塞位置，不宣布全部完成。

## 仅分析已有归档

用 `scripts/capability_review.py prepare/files/read/submit` 或同一 MCP 连接中的 `prepare_capability_review` → 按需 `list_capability_materials` / `read_capability_material` → `submit_capability_review`。先读随材料提供的固定 Skill 与输出要求，只补读关键题原件，完成后一次提交。CLI 保存 `Skill正文.md`、`analysis.json`、报告及回执；字段与材料读取见 [轻量能力分析](CAPABILITY_REVIEW.md)。这些接口不运行模型、任务或检查器。

“同一 Agent 接续”是调用方工作约定；提供正文与保存报告不独立证明其身份、已阅读、语义正确或建议有效。报告记录已有归档中的表现变化，不修改历史分数或评分方法。

## 旧逐题接口与演示

下面保留早期0.1.1逐题接口与离线演示，用于历史兼容，不作为当前默认流程。

1. 在平台“对比”页准备新对比，选择真实 A、真实 B、待补 B，或明确的 U05 离线模拟 B；选择本次逐题清单与已发布的 workflow 版本。
2. 复制外部分析指令，交给已配置平台 MCP 的外部 Agent。也可由外部 Agent 自行调用 `create_comparison`。
3. 外部 Agent 读取固定版本 workflow 和平台合同，逐题读取材料、提交分析，最后提交整体报告与开发建议。
4. 平台分别显示结论、资源指标、证据不足和未覆盖项。结论和建议可以进入对应题目，展开保存的原始证据。

上述逐题流程对应历史方法0.1.1（离线试用），不代替任务自己的完成标准；当前0.10.1使用前面的轻量入口。

0.1.1 在“形成下一步开发方向”中融入工程复盘：先定位事实，再核查已有机制、实际缺口和最小动作，写明改动作用位置及维护代价。导航、检查、指令、工具成本和信息访问只作为适用时的调查方向，不增加评分维度。参考来源及平台字段映射保存在 `references/engineering-retro.md`。

## 外部工具与接口

| 工具 | 职责 |
| --- | --- |
| `get_comparison_contract` | 读取比较、逐题分析、最终报告的 JSON Schema |
| `list_comparisons` / `get_comparison` | 发现对比并读取清单、进度、报告历史 |
| `create_comparison` | 固定 A/B、题目清单、分析方声明和 workflow 版本 |
| `get_comparison_case` | 读取题目、原始指标、材料目录与最新修订号 |
| `read_comparison_material` | 按材料编号和行号读取已核对 SHA-256 的节选 |
| `submit_comparison_case` | 追加一道题的观察、理由、限制与证据引用 |
| `submit_comparison_report` | 引用全部最新逐题分析，提交汇总和开发建议 |

工具通过原有 MCP stdio 服务调用 FastAPI。HTTP 前缀为 `/api/v1/comparisons`；`GET /contract` 返回实际合同。逐题读取为 `GET /{comparison_id}/cases/{case_id}`，提交为 `POST /{comparison_id}/cases/{case_id}/analyses`；整体报告为 `POST /{comparison_id}/reports`。历史报告可通过 `GET /{comparison_id}/reports/{report_id}` 单独读取。

逐题观察包括维度、前后表现、变化结论、理由、限制和材料引用。结论允许改善、退步、有取舍、无明确变化、证据不足、未覆盖。开发建议包括现象、原因判断状态、建议行动、优先理由、验证方式、成功信号、需要保护的行为以及逐题观察引用。

## 保存与可信边界

- 对比计划保存原始运行与清单哈希，固定 workflow 的目录编号、版本编号及内容哈希。已存在的独立检查报告只读取快照，不重新执行。
- 材料引用必须属于本题、指定来源和哈希。节选由服务端读取并保存，调用方不能上传自写节选充当原证据。
- 确定变化需要相同且非空的任务内容，以及 A/B 两侧证据。缺 B 或任务改变时只能保留不确定性，不能作为直接升降结论。
- 原文件被修改，即使清单未更新，也会阻止新的分析；旧报告及已保存的证据节选保留。
- 每题提交带最新 `revision`；重复 `request_id` 仅在载荷完全相同时幂等。新修订和新汇总追加保存，历史报告保存当时引用的逐题副本。
- 汇总不能遗漏计划内题目、引用过期逐题版本或伪造观察编号。已收到全部题目与证据足够是两个独立状态。
- 模拟来源和离线脚本分析的标记由服务端派生，并保留在报告、材料和界面中。模拟 B 不导入真实运行列表，不改变原题或分数。

平台验证格式、范围、引用和材料完整性；不独立证明外部分析的语义或因果判断正确。建议中的“原因有依据”也是分析方的声明，不能据此自动修改 Harness。

## U05 离线基线复盘（0.1.1）

只用真实A归档，B保留缺失，用以下脚本发布或复用新workflow版本，再通过实际MCP读取材料、提交脚本编写的分析和建议：

```powershell
.\.venv\Scripts\python.exe scripts/verify_u05_retro_workflow.py
```

默认回执为 `data/u05-retro-receipt.json`。脚本不执行模型、评测或评分器，仅使用已保存的独立检查结果。报告有5项观察：4项前后比较证据不足、1项未覆盖；这不否认A中的失败事实，而是保留没有真实B时的判断边界。

两条建议分别核查编辑匹配失败与停止时序、既有验证入口。每条写明已有机制、实际缺口、作用位置、最小动作、维护成本与后续验证。原记录已经返回错误，因此不能直接建议重复增加“错误反馈”；缺少成功自测也不能直接推出项目没有测试命令或CI。

## U05 模拟B通道演示

运行前启动本机平台，使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe scripts/seed_comparison_demo.py
```

脚本使用实际 MCP 客户端读取已发布 workflow、U05 真实旧归档和原有独立检查报告，以固定的脚本响应提交逐题分析及整体报告。它会保存或复用独立的 workflow 目录项；不会调用模型、执行被测 Agent、执行归档脚本或运行评分器。默认回执为 `data/comparison-demo-receipt.json`。

示例使用 `harness-boundary20-20261109` 中的 `U05-click-default-help`。A 的真实记录为 30 次模型请求、33 次工具调用、2 次工具错误；事件 97 为补丁匹配断言失败，事件 98 因步数限制停止。耗时展示取归档题级 `metrics.elapsed_seconds`（约 74.77 秒），不混用产物 `result.json.seconds`。

B 是 `u05-offline-v1` 情景：假设修复交付和验证完成，设定 22 次请求、25 次工具调用、312000 累计 tokens、91.2 秒。数字与成功行为均为假设，没有新版执行。费用未记录，上下文压缩质量未覆盖。这个情景用于检查“部分改善伴随资源代价”“证据不足”“未覆盖”的展示，不证明新版更强。

当前示例有 1 道题、7 项观察：5 项给出情景结论、1 项证据不足、1 项未覆盖，另有 2 条开发建议。真实失败支持优先核查编辑失败反馈与恢复流程；不能直接确认责任模块，也不能根据模拟资源数字开展优化。

## 包装与验证

`scripts/package_comparison_workflow.py` 从正式 Skill、参考资料和实际 Pydantic Schema 生成平台单篇文本与目录哈希，仅写文件，不自动发布。Skill API 会去掉正文首尾空白，包装时采用同样口径。

本轮通过独立数据库的 HTTP/MCP 测试、前端指标与证据预览测试、类型检查、生产构建，以及本机浏览器下钻和历史报告切换。完整结果见 `VERIFICATION.md`。离线响应不能替代后续真实外部 Agent 的分析质量验证。
