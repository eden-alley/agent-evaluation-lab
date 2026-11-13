# 共创 Skill

本目录保存共创方法与外部分析 workflow 的源码和平台导入文件。

| Skill | 方法版本 | 职责 |
| --- | --- | --- |
| [通用 Harness 评测](general-harness-evaluation/SKILL.md) | 0.1.5 草稿 | 从风险设计种子题和验收证据，补齐覆盖缺口并准备版本化基线 |
| [结果判定与评分](agent-result-grading/SKILL.md) | 0.2.1 试用 | 内置 Judge 的判分路由、独立报告、证据引用和人工追加复核，与当前能力页同步 |
| [Agent能力分析](agent-version-comparison-workflow/SKILL.md) | 0.3.0 离线试用 | 程序统计指标、解析证据并提交；外部Agent讲清代表题背景、经过与结果，解释取舍并给出开发建议 |

方法的试用状态见各 Skill 正文。平台发布记录见 [Skill 同步记录](../docs/SKILL_SYNC.md)。

## 两种表示

- 各 Skill 子目录保存正文和参考资料。评分 Skill 另含示例 JSON、汇总脚本和客户端元数据。
- `platform/*.json` 是现有 `POST /api/v1/skills/{id}/versions` 可接受的请求体。平台目前只保存单篇文本，因此合并正文与参考资料，并将相对链接改为文内锚点；评分示例与脚本以完整代码块收录。平台不会执行这些代码。
- 能力分析仅默认打包主Skill和短retro清单；[三道题讲解示例](agent-version-comparison-workflow/references/task-explanation-examples.md)与[取证材料](agent-version-comparison-workflow/references/task-explanation-evidence.json)按需读取，不另建任务讲解Skill。打包器按实际API的正文归一化后生成哈希与字符数。
- `catalog.json` 保存目录元数据、方法版本、每个原始文件的 SHA-256 和平台内容哈希。平台哈希采用 `backend/lab/quality_checks.py` 中 `digest({"content": text})` 的规范化算法，并非纯文本字节哈希。

客户端只读取平台内容时，可将示例 JSON 与 Python 代码块保存为标示的相对路径，再执行正文命令。直接使用仓库文件时，从 `skills/agent-result-grading` 目录执行：

```powershell
python scripts/aggregate_scores.py references/example-checks.json
```

脚本只汇总已有标签，不检查原始运行，也不证明评分依据充分。

## 同步到另一个本地实例

数据库属于本机状态，不提交 Git。克隆仓库不会自动发布 Skill；有用户授权后，使用现有接口导入：

1. 启动平台，用 `GET /api/v1/skills` 检查目录。按 `catalog.json` 中的名称匹配；有多个同名项时先确认目标，不自动选择。
2. 没有对应目录时，将该项的 `catalog` 对象提交到 `POST /api/v1/skills`；已有目录则复用它的 ID。
3. 对照已发布内容及哈希；内容完全一致时保留原版本。不同或尚未发布时，将对应 `payload_file` 的 JSON 提交到 `POST /api/v1/skills/{id}/versions`。
4. 通过网页审阅发布，或在用户已授权发布的前提下调用 `POST /api/v1/skills/{id}/versions/{version_id}/publish`。
5. 用 `GET /api/v1/skills/{id}/content` 回读，核对全文、哈希及发布状态，再用 MCP `list_skills` / `get_skill` 验证外部调用方可读取。

方法版本（如 0.1.2）与平台递增版本号（如第 1 版）是不同字段。已有版本不可覆盖，新增版本不得修改历史产物所引用的旧版本。

同步记录及验证边界见 [Skill 同步记录](../docs/SKILL_SYNC.md)。

版本对比的完整接入流程、材料与报告合同及 U05 离线演示见 [对比 workflow 说明](../docs/COMPARISON_WORKFLOW.md)。它不改变已有两份方法或平台评分逻辑。
