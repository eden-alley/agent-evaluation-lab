# O01 · 三表对账与差额归因

## 第 1 轮

财务需要按订单定位预期与到账差额。orders.csv 给出预期金额，settlements.csv 给出结算流水，reversals.csv 给出应抵扣的冲正。三表在 data/ 中；订单号唯一，全部订单预期使用 CNY。流水及冲正金额为正数，两位小数。

两个交易表分别按自己的 id 判重。相同 id 的行若字段全同，只取一笔并记录多出的行数。只要同 id 的行有任何字段冲突，隔离该 id 的所有行，计入冲突，不再作为重复或未匹配交易。然后按下列顺序判断保留的交易：订单不存在记 unknown_order；币种与订单不同记 currency_mismatch；冲正若找不到已匹配成功的原结算记 unmatched_settlement；原结算属于另一订单记 order_mismatch。每笔失败交易只记第一个原因。匹配成功的结算计入 gross，冲正计入 reversal（正数），net = gross - reversal，difference = net - expected。没有匹配结算的订单金额按零计，单独列出。

只交付标准库脚本 reconcile.py 和 reconciliation.json，保留输入文件。脚本入口为 `python -B reconcile.py data reconciliation.json`，支持换数据目录及输出路径。请实际运行并落盘。输出 JSON 对象包括：
- orders：逐订单对象数组，每项有 order_id、expected、gross、reversal、net、difference。
- totals：含相同五个金额字段的汇总对象，所有金额均为两位小数字符串。
- duplicate_rows：对象数组，每项有 table、id、extra_rows（整数）。
- conflicting_ids：对象数组，每项有 table、id。
- unmatched：对象数组，每项有 table、id、reason。
- unmatched_order_ids：订单号数组。table 取 settlements 或 reversals。各数组顺序不限。
