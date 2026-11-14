# 轻量分析的程序接口

当前方法 v0.9.0。准备参数review_scope默认focused；只有formal_batch且选中超过3题才允许整批开发建议。程序随材料保存review_policy，并在提交时拒绝小范围建议。历史记录不改。程序提供完整指标表、`key_case_candidates`、固定Skill正文与版本。候选仅供选择，不要求全部讲解；建议引用的题和明确指定的题必须讲清回复区间、动作、反馈和关键转折。`requirements.explanation_case_ids` 默认为空，不代表不用提供建议的题目依据。每条建议仍需priority_reason与直接证据；已有机制、原因、成功信号和保护项可选补充。程序记录所选讲解、总统计题数及未展开候选，语义和模型遵循未验证。旧版本输出要求和历史报告保持原样。

CLI（仓库根目录，平台 API 已启动）：

```powershell
.\.venv\Scripts\python.exe scripts/capability_review.py prepare <comparison_id> --out <材料目录>
.\.venv\Scripts\python.exe scripts/capability_review.py read <comparison_id> --case U05 --side candidate --path events.jsonl --start 1 --lines 40
.\.venv\Scripts\python.exe scripts/capability_review.py submit --packet <材料目录>/packet.json --analysis <材料目录>/analysis.json
```

程序生成精简材料、`Skill正文.md`、`方法提供记录.json`、按题的材料、程序管理的packet和分析模板。准备使用POST review-materials；原GET入口保留旧协议。建议evidence填写case_id/side/path及事件或检查项；开发建议可省略或为空；没有建议不要求填写no_recommendation_reason，页面不显示空建议区。准备会严格核对原归档；提交前保存固定request，成功才写receipt和report。超时不自动重试，同输入可取回同一回执；他人已提交较新分析则返回409。

MCP 使用同一条连接：`prepare_capability_review(comparison_id)`、按需 `read_capability_material`、`submit_capability_review(comparison_id, analysis)`。程序保管准备时的修订状态；重新连接后需重新准备。材料变更、调用失败、参数错误和提交冲突分别返回明确错误。

HTTP：`GET /api/v1/comparisons/{id}/review-materials` 读取固定快照并计算统计，不自动扫描原件；`POST .../verify` 严格校验；`GET .../review-material` 按题号、侧和文件路径补读；`POST .../review` 校验程序信封后，在同一事务中追加逐题记录和整体报告。

发布 Skill 时仅打包主 Skill 与短复盘清单。指标定义在程序注册表中版本化，具体适用题、原检查项与排除理由随报告保存。缺乏统一判据的语义维度显示未评估；没有新增模型评分器。

`case_explanations` 只填选择展开的关键题（或建议依据题、明确指定题），没有必须讲满的数量。参照生成的 `analysis-format.json` 和仓库中的 `examples/capability-review/u05-explanation-offline.json`。逐段引用用A/B侧、文件路径及事件编号/检查项编号；多轮重置编号时使用实际行号且line_count为1。程序固定引用和简洁预览。新版报告 `explanation_coverage.mode=key_cases`，分别记录total_cases、实际讲解和unexpanded_candidate_case_ids，平台不以讲解题数/全部题数显示未完成进度。原有全量指标与评分不变。
