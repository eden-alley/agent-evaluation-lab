# 轻量分析的程序接口

当前协议 v0.2.0。程序准备和提交，分析者只填写分析文档。旧逐题接口和 JSON Schema 保留供历史调用兼容，不再打包进每次分析的 Skill。

CLI（仓库根目录，平台 API 已启动）：

```powershell
.\.venv\Scripts\python.exe scripts/capability_review.py prepare <comparison_id> --out <材料目录>
.\.venv\Scripts\python.exe scripts/capability_review.py read <comparison_id> --case U05 --side candidate --path events.jsonl --start 1 --lines 40
.\.venv\Scripts\python.exe scripts/capability_review.py submit --packet <材料目录>/packet.json --analysis <材料目录>/analysis.json
```

程序生成精简的 `材料摘要.md` / `materials.json`、按题的 `cases/<题号>.json`、程序管理的 `packet.json`、`analysis.json`、`analysis-format.json` 和指标 Markdown。准备会严格核对原归档；补读只接受归档目录内的文件；提交前把固定请求保存为 `request.json`。成功才写 `receipt.json` 和 `report.json`。超时不会自动重试，用同一材料包和分析再次提交可取回原回执。材料后有其他人提交分析时返回409，重新准备后再决定是否提交。

MCP 使用同一条连接：`prepare_capability_review(comparison_id)`、按需 `read_capability_material`、`submit_capability_review(comparison_id, analysis)`。程序保管准备时的修订状态；重新连接后需重新准备。材料变更、调用失败、参数错误和提交冲突分别返回明确错误。

HTTP：`GET /api/v1/comparisons/{id}/review-materials` 读取固定快照并计算统计，不自动扫描原件；`POST .../verify` 严格校验；`GET .../review-material` 按题号、侧和文件路径补读；`POST .../review` 校验程序信封后，在同一事务中追加逐题记录和整体报告。

发布 Skill 时仅打包主 Skill 与短复盘清单。指标定义在程序注册表中版本化，具体适用题、原检查项与排除理由随报告保存。缺乏统一判据的语义维度显示未评估；没有新增模型评分器。
