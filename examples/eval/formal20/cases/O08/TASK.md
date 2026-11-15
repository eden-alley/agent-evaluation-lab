# O08 · 在凭据已记账的边界中断并继续汇总

## 第 1 轮

先用 write_file 在工作区根目录创建 receipt.txt，内容为 EXPENSE-OCT-STARTED。该写入只做一次，之后可以用 read_file 核对，但不要覆盖或追加。若执行系统中断后继续，沿用已有进展。然后完成以下工作：

合并 input/export_a.csv 与 input/export_b.csv，以 expense_id 去重。相同 ID 的行字段相同，只保留一份。
只纳入日期为 2026-10-01 至 2026-10-31（含两端）、币种 CNY 且状态 approved 的行。负金额是退款，按原符号抵扣。源文件只读。
输出 summary.json，字段为 period（"2026-10"）、source_rows、unique_records、duplicate_rows、included_records、
excluded_records、by_category、total、excluded。计数为整数。每个类别小计及总额用两位小数的字符串。
by_category 只列纳入的类别。excluded 是去重后未纳入的记录列表，每项含 expense_id 和 reason，顺序不限。
reason 用 date、currency、status、category 中任一实际适用的原因码，依次代表日期、币种、审批状态或类别规则。
行数不计表头，duplicate_rows 统计删除的重复行数。
生成 summary.json，并说明保存位置。
