# 轻量能力分析 v0.3.0

目的：把已有归档变成逐指标升降、题目依据与少量开发建议。程序负责材料读取、统计、固定引用和一次提交；外部 Agent 只解释事实、取舍与待验证的原因。

本模块不调用模型、不运行评测或检查器、不修改原评分。上下文质量、无效重复、恢复质量、简洁度与工具策略等没有确认判据的维度保持未评估。

## 使用

平台启动后，在仓库根目录：

```powershell
.\.venv\Scripts\python.exe scripts/capability_review.py prepare <对比编号> --out <材料目录>
.\.venv\Scripts\python.exe scripts/capability_review.py files <对比编号> --case U05 --side candidate --query events
.\.venv\Scripts\python.exe scripts/capability_review.py read <对比编号> --case U05 --side candidate --path events.jsonl --start 1 --lines 40
.\.venv\Scripts\python.exe scripts/capability_review.py submit --packet <材料目录>/packet.json --analysis <材料目录>/analysis.json
```

优先给分析者 `材料摘要.md`、`materials.json` 和已发布 Skill；需要时读取 `cases/<题号>.json` 或原件。完整 `packet.json` 由程序保管，不必让 Agent 整份读入。`analysis-format.json` 是程序生成的文档格式，分析不必处理提交信封。

MCP：同一连接中调用 `prepare_capability_review`，按需 `list_capability_materials` / `read_capability_material`，再 `submit_capability_review`。程序为该连接保管准备时的材料和修订状态；重连需重新准备。旧逐题接口仍兼容。

更新之前已经启动的 MCP 客户端需要重新连接以发现新增工具；CLI入口可以直接使用。MCP 的准备与回执只返回精简摘要，完整证据由程序保存并按需读取。

## 逐题过程讲解

任务过程讲解已经融入现有能力分析Skill，不新增独立Skill或分析阶段。先看指标，再选取值得补读的代表题，讲清任务背景、关键动作与反馈、完成情况和停止位置。

分析文档可选 `case_explanations`。每题包含 `case_id`、明确的 `focus`（baseline/candidate/comparison）、`background`、最多8段 `stages`、`result` 与限制条件。阶段含标题、正文和证据；结果含正文和证据。证据只填 `side`、材料路径及 `event_id` 或 `check_id`，普通文本也可指定行范围。程序解析行号、摘要和原件节选，不让分析者编写材料UUID或哈希。

引用须属于固定清单中的该题及指定A/B侧；缺失或重复事件、错误检查项、来源混用会在写入前被拒绝。报告与逐题内容在同一事务保存，历史报告不受后续讲解影响。`explanation_coverage` 单独记录讲解题数，不与指标覆盖或题目记录收齐混为一谈。

未提供讲解的题目保留原统计，并显示“尚未提供过程讲解”；新报告不自动继承旧报告的讲解。原有不含讲解字段的输入与历史提交编号仍兼容。

`examples/capability-review/u05-explanation-offline.json` 是正式20题中CLI限制查询任务的离线讲解样例，仅深入讲解真实B运行。它保留功能通过、报告完成、原测试被改动及README越界的各项事实，也保留自测项自动值0与复核后有效值1的历史，不做新的判分。

平台详情先展示任务背景和完成情况，再展示分阶段经过，依据按需展开；原题、判据、资源和原始材料仍可查看。事件预览省略文件指纹清单，保留固定原件哈希、行号及可回查的原始节选。默认Skill正文只包含必要指引和短retro清单，完整案例与取证JSON保留在参考文件中。

打包器使用与平台相同的 `SkillContent` 归一化正文，再计算哈希和字符数，避免末尾换行导致导入后的哈希变化。API导入、发布与引用链路有回归测试。更新前已连接的MCP客户端需重连以刷新可选讲解字段。

成功后保存 `receipt.json`、`report.json` 与带建议的 `指标升降表.md`。没有回执时不能宣称平台已收到。

## 指标口径

注册表：`backend/lab/comparisons/metrics.py`，版本 `saved-checks-0.2.0`。修改分组或统计含义时必须升级版本；历史报告保存统计、逐题证据和口径，不随新代码重算。

| 指标 | 原归档字段 |
| --- | --- |
| 原任务整体完成 | core_acceptance；要求双方必需检查ID/规则一致，且为明确pass/fail |
| 代码任务独立回归 | independent |
| 最终代码有效自测 | agent_tested_final_change / agent_tested_final |
| 任务修改范围遵守 | scope / protected_files |
| 明确报告交付 | delivery / report / change_report |
| 显式定位说明 | localization |

每题每指标只计一次；同一指标多个对应检查全部通过才计该题通过。只使用两版同题、同检查ID集合、同规则且有效的0/1结果。缺项、规则变化、无效或未知结果排除并说明，未适用题不计零。原整体完成只是原判定的统计，不是新的端到端裁决。

资源包括模型请求、归档tool_call数量、归档失败tool_result数量、累计输入/输出tokens与题级耗时之和。只比较双方都有有效计数的同题记录。资源不是能力分；累计tokens不是峰值上下文，耗时之和不是批次挂钟时间。

平台分别显示质量覆盖、资源覆盖和未评估维度。收齐全部题目记录不意味着全部维度已经评估。净改善也必须展示具体回归题；不合成跨维度总分。

## 可靠提交

程序信封包含材料包哈希、固定Skill版本、准备时的报告/逐题修订和确定性请求编号。分析文档只包含摘要、最多3条建议和限制条件。建议通过指标ID和适用题目关联证据。

- 严格原件扫描在写事务之前完成，一次请求内复用；列表、历史报告和目录读取不重复扫描。
- 一次事务追加全部逐题记录和整体报告，任何错误回滚全部写入。
- 相同材料包及分析的重复提交返回原回执；相同编号不同内容返回409。
- 准备后有人提交新分析则返回409，不静默替换较新工作。新材料包需要重新分析确认。
- 原件改变时拒绝新的报告；已有报告与节选仍可查看，并显示最近完整校验状态和时间。
- 超时与非JSON响应分别报告，写入状态保持“尚未确认”；不自动重试、不自动换请求编号。

## 离线样例与边界

`examples/capability-review/real20-offline-analysis.json` 是针对现有两次20题真实归档离线整理的建议，不是LLM Judge输出。提交样例时使用 `--origin offline_program`，页面会明确显示程序统计及离线建议。

该样例原整体完成11/19→13/19，范围遵守20/20→16/20。O07的pass→unknown不计退步；资源仍包含20题。两次请求预算30→60且其他运行条件也改变，只支持本次归档表现，不能证明稳定能力或单个Harness改动的因果。

retro适配版只用于核查已有机制、实际缺口和最小验证动作。未核查的实现写“尚未核查”；原因状态只允许待验证或未确定，不把问题现象当作责任归因。自动统计已通过离线验证，模型遵循Skill的质量未做调用或校准。
