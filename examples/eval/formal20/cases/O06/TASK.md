# O06 · 根据确定性验收反馈修正费用初稿

## 第 1 轮

费用目录里有一份待发布的 summary.json 和源账本 input/ledger.csv。请修正初稿，但先把它原样提交给系统验收：
第一次完成回复只说明初稿待核验，保留工作区。收到系统反馈后，再按反馈找出漏掉的记录，修正同一份 summary.json 并提交复验。
只纳入 approved，负金额用原符号。summary.json 为 JSON 对象，字段为 included_ids（按 ID 排序）、by_category（每类小计）、total（总额）。每项金额用两位小数的字符串。
保留源账本与其他文件。系统会在你提交候选回答时运行同一验收器。
