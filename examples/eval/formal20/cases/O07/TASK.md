# O07 · 压缩后保留最后一次报销规则更正

## 第 1 轮

合并 input/export_a.csv 与 input/export_b.csv，以 expense_id 去重。相同 ID 的行字段相同，只保留一份。
只纳入日期为 2026-10-01 至 2026-10-31（含两端）、币种 CNY 且状态 approved 的行。负金额是退款，按原符号抵扣。源文件只读。
输出 summary.json，字段为 period（"2026-10"）、source_rows、unique_records、duplicate_rows、included_records、
excluded_records、by_category、total、excluded。计数为整数。每个类别小计及总额用两位小数的字符串。
by_category 只列纳入的类别。excluded 是去重后未纳入的记录列表，每项含 expense_id 和 reason，顺序不限。
reason 用 date、currency、status、category 中任一实际适用的原因码，依次代表日期、币种、审批状态或类别规则。
行数不计表头，duplicate_rows 统计删除的重复行数。
我们分阶段工作：先记住规则，暂不生成最终汇总。允许在工作区保留自己的笔记。

## 第 2 轮

更新口径：先排除学习类别。最终 JSON 改存 reports/reimbursement.json。其他要求照旧。这一轮只记录更改，不生成汇总。

## 第 3 轮

财务补充了退款例外：学习类别的正向与零金额记录仍排除，但若一笔学习退款为负数，且符合月份、币种与审批条件，则纳入并按负数抵扣。第二轮的输出路径及其他规则照旧。本轮只报告导出总行数和重复 ID，不复述报销规则，也不生成汇总。

## 第 4 轮

检查输入是否都有非空 expense_id，以及日期是否都符合 YYYY-MM-DD。只汇报这两项数据质量结果，不复述汇总规则，不生成汇总。

## 第 5 轮

现在按最后确定的规则和保存位置生成最终 JSON，并说明文件在哪里。
