# 轻量分析的程序接口

当前方法 v0.10.1。已获授权发起评测的同一外部 Agent 在同一任务接续分析和提交；只读归档分析不授予新模型调用、重跑或重评授权。程序不启动分析 Agent，也不证明调用方身份或确已阅读。旧版本输出要求和历史报告保持原样。

## 日常评测入口

在仓库根目录使用 `python scripts/evaluation.py --help` 查看实际合同。新运行先显式同步或复用本版 Skill，保存命令返回的 `workflow` 三字段（`skill_id`、`version_id`、`content_hash`）到配置，不暗选基线或方法：

```powershell
.\.venv\Scripts\python.exe scripts/evaluation.py sync-skill --api-url <明确本机平台地址>
.\.venv\Scripts\python.exe scripts/evaluation.py start --config <假模型验证配置.json> --out <新运行目录>
```

`start --config` 只允许 `scripted_api` 且 `validation=true`，不是付费模型授权。真实供应商执行先冻结配置，向用户展示本轮模型、题目、预算上限、重试和 Judge 策略；仅在本轮明确批准后使用批准的同一文件与哈希：

```powershell
.\.venv\Scripts\python.exe scripts/evaluation.py freeze --config <真实执行配置.json> --out <冻结plan.json>
.\.venv\Scripts\python.exe scripts/evaluation.py start --plan <已批准plan.json> --approved-plan-sha256 <当轮批准哈希> --out <新运行目录>
```

配置须显式绑定执行源码、模型、冻结题目/题号，以及 `delivery` 的平台地址、数据目录、归档目录、项目/运行身份、基线、固定 workflow 和分析用途；细节见 [日常接入](../../../docs/EXTERNAL_AGENT.md) 与入口 `--help`。验证只能使用隔离平台和目录。没有 A 时须明确只建基线：假模型验证使用 `--baseline-only`，真实供应商首批基线须在批准前将 `baseline_only=true` 写入冻结计划；不报告升降，不在执行时改变批准范围，也不能替用户选择 A。

执行完整结束后程序归档、导入、统计并准备固定材料；返回 `analysis_pending` 时，同一 Agent 继续：

```powershell
.\.venv\Scripts\python.exe scripts/evaluation.py continue --run <原运行目录>
# 读取返回 control_dir 中的固定 Skill正文.md 和材料，填写 analysis.json。
.\.venv\Scripts\python.exe scripts/evaluation.py submit --run <原运行目录> --analysis <分析文件.json>
```

`continue` 读取同一次任务状态，按已保存状态安全恢复执行或仅继续收尾，不是新一轮评测。材料、原请求和绑定已存在时复用。`analysis_pending` 不等于全部完成；必须取得对应 `report.json`、`receipt.json` 和 `delivery_complete` 后才宣布报告交付完成。显式只建基线返回 `baseline_required`、`task_complete=true`、`report_complete=false` 时，只宣布基线保存完成，不声称已有 A/B 分析或升降结论。

## 仅分析已有归档

准备参数 `review_scope` 默认 `focused`；只有 `formal_batch` 且选中超过3题才允许整批开发建议，也可为空。程序随材料保存 `review_policy` 并校验。候选仅供选择，不要求全部讲解；建议引用的题和明确指定的题必须讲清回复区间、动作、反馈和关键转折。`requirements.explanation_case_ids` 默认为空，不代表不用提供建议的题目依据。每条建议仍需 `priority_reason` 与直接证据；已有机制、原因、成功信号和保护项按需补充。

以下入口只分析已有对比，不执行评测；日常评测优先用上述 `evaluation.py submit` 保持收尾状态一致。CLI（仓库根目录，平台 API 已启动）：

```powershell
.\.venv\Scripts\python.exe scripts/capability_review.py prepare <comparison_id> --out <材料目录>
.\.venv\Scripts\python.exe scripts/capability_review.py read <comparison_id> --case U05 --side candidate --path events.jsonl --start 1 --lines 40
.\.venv\Scripts\python.exe scripts/capability_review.py submit --packet <材料目录>/packet.json --analysis <材料目录>/analysis.json
```

程序生成精简材料、`Skill正文.md`、`方法提供记录.json`、按题材料、程序管理的 packet 和分析模板。准备使用 POST review-materials；原 GET 入口保留旧协议。建议 evidence 填写 case_id/side/path 及事件或检查项；建议可省略或为空，没有建议不要求 no_recommendation_reason。程序记录所选讲解、总统计题数及未展开候选，语义和模型遵循未验证。

提交前固定 request，成功才写 receipt 和 report。超时不自动重试，同输入可取回同一回执。日常入口保存明确拒收后，将修正稿另存文件，再对同一运行调用 `evaluation.py submit --run <原目录> --analysis <修正文件>`；程序保留原失败尝试、关联后续提交并更新原任务回执。不要手改原 request 或失败 analysis。读取 `continue` 返回的当前材料位置，详见 [收尾恢复约定](../../../docs/REAL_RUN_DELIVERY.md#恢复)。prepare 响应丢失仍不能自动另造 delivery。

MCP 使用同一条连接：`prepare_capability_review(comparison_id)`、按需 `read_capability_material`、`submit_capability_review(comparison_id, analysis)`。程序保管准备时的修订状态；重新连接后需重新准备。材料变更、调用失败、参数错误和提交冲突分别返回明确错误。

HTTP：`GET /api/v1/comparisons/{id}/review-materials` 读取固定快照并计算统计，不自动扫描原件；`POST .../verify` 严格校验；`GET .../review-material` 按题号、侧和文件路径补读；`POST .../review` 校验程序信封后，在同一事务中追加逐题记录和整体报告。

发布 Skill 时仅打包主 Skill 与短复盘清单。指标定义在程序注册表中版本化，具体适用题、原检查项与排除理由随报告保存。缺乏统一判据的语义维度显示未评估；没有新增模型评分器。

`case_explanations` 只填选择展开的关键题（或建议依据题、明确指定题），没有必须讲满的数量。参照生成的 `analysis-format.json` 和仓库中的 `examples/capability-review/u05-explanation-offline.json`。逐段引用用A/B侧、文件路径及事件编号/检查项编号；多轮重置编号时使用实际行号且line_count为1。程序固定引用和简洁预览。新版报告 `explanation_coverage.mode=key_cases`，分别记录total_cases、实际讲解和unexpanded_candidate_case_ids，平台不以讲解题数/全部题数显示未完成进度。原有全量指标与评分不变。
