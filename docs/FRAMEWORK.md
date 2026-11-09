# 当前实现与边界

以 `EXTERNAL_AGENT.md` 和用户 2026-11-06 的最新纠正为准：外部 Coding Agent 调用平台，Skill 方法内容需要共同设计。

真实能力：项目注册、被测 Agent 静态检查、MCP 工具接入、用户内容的 Skill 版本发布、不可变数据集草案、程序校验、外部质量报告、原文证据定位、人工审阅与固定版本。

示例能力：被测 Agent 的评测运行、评分结果、运行 Trace、两次运行比较。仍未接入真实执行器。

平台只存储/提供技能文本，不执行技能。仓库现已收录用户共创确认的通用 Harness 评测 v0.1.2 与结果判定和评分 v0.1.0，见 [Skill 目录](../skills/README.md)；导入并发布后可供外部工具读取。原内置 dataset-design 占位项仍未发布，不会被声明为可用。

## 核心接口

- 项目：GET/POST /api/v1/projects；PATCH /projects/{id}；GET /projects/{id}/context。
- 被测程序：GET/PUT /projects/{id}/agent；POST /projects/{id}/agent/check。
- 连接：GET /integration；GET /integration/contract。
- 技能：GET/POST /skills；GET /skills/{id}；POST /skills/{id}/versions；POST /skills/{id}/versions/{version_id}/publish；GET /skills/{id}/content。
- 草案：POST /dataset-drafts；GET /projects/{id}/dataset-drafts；GET /dataset-drafts/{id}。
- 报告：POST /dataset-drafts/{id}/reports；GET /dataset-drafts/{id}/reports/{report_id}。
- 人工决定：POST /dataset-drafts/{id}/decision。
- 固定版本：GET /projects/{id}/dataset-versions；GET /dataset-versions/{id}。

以上省略的前缀均为 /api/v1。提交合同由 /integration/contract 直接生成 JSON Schema。错误返回 error.code/message/details，敏感输入值不在校验错误中回显。

## 约束

草案和报告请求不超过 2 MiB，每份草案 1–500 个案例、1–100 项需求。草案内容不可覆盖；报告追加保存。唯一请求编号只对相同载荷去重。确认要求最新报告、完整检查、无阻断项和当前基准版本；警告或覆盖缺口需要接受说明。版本固定内容、程序发现、报告、Skill来源与人工决定。

## 后续

两份首版方法已进入试用阶段；后续需在外部 Coding Agent 中验证实际设计与判定质量，再按确认范围接入被测 Agent Worker、真实执行事件和评分。问题分析方法暂不开展。离线接口测试不能替代方法质量或真实模型验收。
