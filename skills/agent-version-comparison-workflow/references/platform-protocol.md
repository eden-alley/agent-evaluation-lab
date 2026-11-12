# 平台协议 v1

本流程由外部 Agent 发起，不由平台启动 CLI。分析只消费已有运行；读取归档中的代码与命令不表示获准执行它们。

## 操作顺序

1. 用 `get_comparison_contract` 取得实际 JSON Schema；`list_comparisons` 可发现已建对比。
2. 用已发布 workflow 的 skill_id、version_id、content_hash，调用 `create_comparison(comparison=...)` 固定范围。普通比较的 candidate 为 `{kind: "run", run_id: "实际运行编号"}`；只有离线验证才选 `{kind: "simulation", fixture_id: "u05-offline-v1"}`。缺少B时选择 `{kind: "missing"}`。
3. `get_comparison` 返回队列、收到的题数和报告历史。对每题调用 `get_comparison_case`，读取任务、原检查结果、资源事实、材料目录和当前 revision。
4. `read_comparison_material` 用材料编号按需取证，每次最多200行。引用必须保留实际 material_id、sha256 和行范围；不得用自己写的节选代替原材料。
5. `submit_comparison_case` 提交该题分析。revision 使用刚读取的值，request_id 使用本次操作的稳定编号。收到报告id后再处理下一题。网络重试复用相同编号及内容；修订使用新请求编号和最新revision，旧报告不会覆盖。
6. 队列中每题都有处理结果后，`submit_comparison_report` 引用所有题目最新报告id，提交汇总和开发建议。get_comparison 可核对回执，指定 report_id 可读取历史汇总。

## 机器字段

逐题报告使用 `request_id`、`revision`、`summary`、`observations`。每个观察项包含：

- `id`：本题内唯一编号；`dimension`、`title`：已有观察方向。
- `before`、`after`：简短的实际事实或null，不编造缺失值。
- `outcome`：`improved`改善、`regressed`退步、`mixed`有取舍、`unchanged`无明确变化、`insufficient`证据不足、`not_covered`未覆盖。
- `reason`与`limits`：依据及结论范围。
- `evidence`：实际材料的 material_id、sha256、start_line、line_count。前四类变化需要同题的A/B双方证据。任务缺失或变化时先记录不可直接比较。

整体报告使用 `request_id`、`case_report_ids`、`summary`、`findings`、`recommendations`。findings和recommendations通过 `{case_id, observation_id}` 引用逐题观察。最终报告不重写原验收结果，也不自行生成新总分。

每条开发建议包括 title、phenomenon、cause_status、cause、action、priority_reason、validation、success_signals、guardrails和refs。cause_status可为hypothesis、supported、unresolved；supported仍是外部分析方的声明，不等于平台已证明因果关系。

准确字段和限制以平台返回的协议及本包schema为准：

- [逐题提交schema](case-analysis.schema.json)
- [整体报告schema](final-report.schema.json)

## 结果解释与中断

平台分别计算“已收到几题”和“多少观察项给出了结论”。每题都分析完仍可能证据不足。源材料漂移会阻止新的提交；历史报告及已验证节选仍保留。

模拟来源由平台确定。即使情景中的修复或验证假设为成功，也只能称为模拟验证。离线脚本提交的分析不是LLM Judge实测，不宣称完成了判断质量校准。

若流程中断，使用原比较编号恢复并读取队列/revision；不要重新猜测已经提交过哪些题。只有平台返回的报告编号能证明提交成功。
