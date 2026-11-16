# U04 修改范围离线校准

规则 `u04-test-scope/1.0.0` 对应冻结题集 `harness-formal-20-v0.2` 的 U04。题面写明“保留已有测试；可新增回归测试”，因此不能只因原测试文件哈希改变就判修改范围失败。

这是独立复核工具：仅重算 `scope`，把结果写入新的 JSON。旧判分器、成绩、评测轨迹和 Lab 数据库均不修改；不调用模型，不执行归档代码，不重新运行公开或独立功能测试。

## 判据

- `1`：原模块、原类、原方法、断言和初始化的 AST 保留；只追加不重名且能够识别的普通测试方法。注释变化不构成原测试改写。
- `0`：原测试被删除、修改、跳过、同名覆盖，新增代码替换测试生命周期，或提交不能通过 Python 编译检查。
- `unknown`：额外模块代码、动态操作、未知方法调用、另建测试文件、其他范围改动等不能自动确认的情况。需要人工复核，不自动转成通过。另建文件即使符合旧判分器的命名白名单，也可能在测试发现时覆盖原方法，因此本规则不直接放行。

AST 是 Python 的语法结构。检查不证明任意新增代码与原代码在行为上等价。自动认可范围有意限制在本题固定测试的普通断言、局部计算、只读请求和每例独立临时数据库操作。更复杂但合理的回归测试可能仍返回 `unknown`。

## 使用

在 Lab 根目录运行（替换尖括号内路径）：

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts\calibrate_u04_scope.py --fixture "<suite>\cases\U04" --case-dir "<saved-run>\paid-run-bailian\U04" --output "<separate-review-directory>\u04-scope-review.json"
```

程序固定题面、原测试及完整输入目录哈希，并要求 `result.json` 的 `source_hashes` 与保存的 workspace 一致。它还重新核对旧 `scope` 的越界文件清单。输入不是固定版本、保存结果与工作区不一致或旧判分证据不一致时拒绝生成报告。

输出必须在整个源题集和源运行目录之外；现有文件绝不覆盖。每次复核使用新的文件名。报告记录来源路径、哈希、规则版本、实现哈希、原成绩和新 `scope`。

`conditional_verdict` 表示“若接受本次范围复核，并沿用其他历史判据”的整题结论。它不是新一轮真实评测成绩。`historical_checks_reexecuted=false` 明确说明其他判据没有重跑。

## 离线检查

```powershell
cd backend
..\.venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_u04_scope.py tests/test_u04_calibration.py
```

固定样例包含本次归档的原测试与追加版本；测试只解析、编译文本，不导入执行它们。覆盖正常追加、原断言篡改、跳过和同名覆盖、生命周期变化、动态修改、不可编译方法、另建测试文件覆盖原方法、无效输入、Python 3.11 AST 字段兼容、未知结论保留、其他历史失败保留及报告防覆盖。
