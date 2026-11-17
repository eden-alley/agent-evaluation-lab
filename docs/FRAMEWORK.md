# 当前实现与接口导航

本页只说明实现边界与查阅入口。先理解主线请读 [架构与执行流程](../ARCHITECTURE.md)；判断当前缺陷与后续取舍请读 [项目现状与取舍](PROJECT_REVIEW.md)；其余材料见 [文档目录](README.md)。

## 当前实现边界

- **执行在外部 CLI。** 日常入口是 [`scripts/evaluation.py`](../scripts/evaluation.py)，串联执行、归档、导入、统计和后续分析交接。已有真实执行链、评分归档、逐题 Trace 和两次运行比较，不能再统称为“仅示例”。示例、假模型验证与真实运行仍须按各自记录区分。
- **平台不启动被测 Agent 的执行 Worker。** FastAPI 的健康接口明确返回 `evaluation_execution=false`；平台负责保存、展示和提供接口。这不等于整个仓库没有执行器，也不否认平台另有 Judge、检查重跑等接口。
- **原评分与后续分析分离。** 执行阶段的原评分随运行归档；比较统计、关键题解释和报告交付在其上组织，不改写原评分。报告回执证明提交的结构与引用通过程序校验，不独立证明分析语义正确。
- **日常入口仍有依赖。** 当前 `start` 在执行前要求明确的平台、交付配置与固定分析 Skill；A/B 分析还需基线，或显式选择只建基线。让核心评测独立于分析 Skill 和报告是后续方向，尚不能当作已经完成的解耦。
- **Skill 由外部 Agent 读取。** 平台管理技能目录、不可变版本和人工发布，不在平台进程内执行 Skill 内容；日常分析由发起评测的同一外部 Agent 接续。

## 操作入口

| 需要做什么 | 说明 |
| --- | --- |
| 发起已获授权的评测、接续与提交 | [外部 Agent 接入](EXTERNAL_AGENT.md) 的“日常评测与分析接续”；执行参数见 [执行入口](../scripts/README-formal20-concurrent.md) |
| 只分析已有归档 | [轻量能力分析](CAPABILITY_REVIEW.md) |
| 理解比较、材料与报告 | [比较流程](COMPARISON_WORKFLOW.md) · [真实运行后的归档与报告交付](REAL_RUN_DELIVERY.md) |
| 导入已有运行、查看评分与证据 | [外部运行导入](EXTERNAL_RUN_IMPORT.md) · [Judge 证据](JUDGE_EVIDENCE.md) |

配置、Skill 和旧运行记录均不构成新增模型调用、重跑或重评授权；具体执行边界按本轮授权与操作文档执行。

## 接口与合同到哪里查

HTTP 接口以当前 router 与 schema 为准，统一前缀为 `/api/v1`。本页不复制完整字段、限制和错误合同，避免形成第二份过期说明。

| 领域 | 当前实现与合同入口 |
| --- | --- |
| 应用装配、健康状态 | [`main.py`](../backend/lab/main.py) |
| 项目、被测 Agent 注册与静态检查 | [`projects.py`](../backend/lab/projects.py) · [`agents.py`](../backend/lab/agents.py) · [`schemas.py`](../backend/lab/schemas.py) |
| MCP 接入、工具清单与项目上下文 | [`integration.py`](../backend/lab/integration.py) · [`mcp_server.py`](../backend/lab/mcp_server.py) |
| 运行、逐题 Trace 与归档原件读取 | [`evaluation_imports.py`](../backend/lab/evaluation_imports.py) |
| Judge、人工复核与检查重跑 | [`judging.py`](../backend/lab/judging.py) · [`judge_contracts.py`](../backend/lab/judge_contracts.py) · [`rechecking/routes.py`](../backend/lab/rechecking/routes.py) |
| 比较、分析材料与报告 | [`comparisons/routes.py`](../backend/lab/comparisons/routes.py) · [`comparisons/schemas.py`](../backend/lab/comparisons/schemas.py) · [`comparisons/review_schemas.py`](../backend/lab/comparisons/review_schemas.py) |
| Skill 目录、版本与发布 | [`skills.py`](../backend/lab/skills.py) · [`schemas.py`](../backend/lab/schemas.py) |
| 数据集草案、质量报告、人工决定与固定版本 | [`quality_routes.py`](../backend/lab/quality_routes.py) · [`quality_schemas.py`](../backend/lab/quality_schemas.py) |

草案提交 JSON Schema 由 `GET /api/v1/integration/contract` 提供；比较分析合同由 `GET /api/v1/comparisons/contract` 提供。调用方应读取当前合同，不据此页拼装请求。

## 旧草案模块的定位

不可变数据集草案、追加质量报告、人工确认与固定版本仍有接口和存储实现，可供现状检查及后续取舍参考。**自动生成评测题已被排除出产品方向**；旧模块尚存，不代表继续建设自动出题，也不代表本轮已经删除模块或迁移历史数据。

固定 golden set 的题单、尺度和校准规则仍待围绕真实任务核验。草案审批流程与日常执行链并非同一条主线，不能把它们都列为单题核心评测的固有前置。