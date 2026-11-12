# 外部 Coding Agent 接入与质量报告交接

2026-11-12 评分接入已交付。Coding Agent 通过 list_evaluation_runs 发现运行，get_evaluation_run 确认实际案例范围，用 get_skill 固定已发布评分版本，再调用 start_judgment。get_judgment 默认返回概要，指定 case_id 后读取逐项判定与证据引用；get_evaluation_evidence 按行读取清单内原件。当前 archive 与 mock 均为离线模式，模型请求为0。人工终判入口位于网页，本机用户追加理由和决定后保留审计记录。工程依据见 JUDGE_EVIDENCE.md。

本增量依据 2026-11-06 用户纠正与实施授权：用户在外部 Coding Agent 中工作，由它调用平台。用户进一步澄清“不要写 Skill”指具体方法内容必须共同设计；内置 Skill 是平台核心，必须支持按需使用并根据需求生成评测集。本增量实现目录、版本草稿、人工发布、按需发现与产物绑定，不代写任何正式 Skill 方法或业务指令。调用方向替代旧技术设计中的“平台启动 Codex”。既有 Python Agent 注册仍指向被测对象。

## 范围与责任

外部 Agent 通过 MCP stdio 工具读取项目目标、提交不可变用例草案、提交外部质量报告、读取保存的结果。MCP 适配层通过现有 FastAPI 调用业务服务，不直接修改数据库。网页负责审阅报告、拒绝或确认生成固定版本。只新增官方 MCP SDK；不启动付费模型或改动被测 Harness。

平台负责格式/引用/唯一性校验、精确重复检测、报告与内容哈希绑定、持久化和版本确认。外部报告的检查方法由调用方决定，平台不生成质量 Skill 或模型评语。记录声明的客户端与实际引用的已发布 Skill 版本/哈希，不视为经过独立验证的质量保证。

## 内置 Skill 支撑

- 保留“评测集设计”的内置目录项，方法内容为空、状态为待共创，不向工具端伪装为可用 Skill。业务 Skill 由用户按实际业务创建。
- 用户在内置技能页保存亲自提供的内容，形成不可变版本草稿；点击发布后才可由外部 Agent 发现和读取。
- MCP list_skills 可按任务关键词与分类筛选元数据；由外部 Agent 根据适用说明选择，平台不声称关键词匹配等于语义推荐。get_skill 只返回已发布的具体版本。
- 外部 Agent 使用 Skill 生成草案时，source.skills 记录 skill_id、version_id、content_hash；平台校验引用存在且已发布。后续发布新 Skill 版本不改变旧数据集的来源。
- Skill 内容仅作为外部 Agent 可读取的文本，不在平台进程内执行代码。

## 数据合同

- 草案：project_id、name、task_description、requirements[{id,description}]、cases[{case_id,title,input,expected,categories,requirement_ids,grading_notes}]、source{client,skills[{skill_id,version_id,content_hash}]}、base_version_id、request_id。source 兼容可选的 skill_name、skill_version 声明，精确来源以 skills 引用为准。1–500 条案例，1–100 项需求；JSON 请求不超过 2 MiB。案例 ID 唯一且需求引用必须存在。
- 每份草案不可原地编辑；修订提交新草案。同名数据集属于同一项目，确认形成连续版本。已有版本时必须引用当前 base_version_id，过期草案不能覆盖新版本。
- 质量报告：request_id、draft_hash、source、summary、reviewed_case_ids、coverage[{requirement_id,status,case_ids,reason}]、findings[{id,severity,category,case_ids,requirement_ids,evidence,suggestion}]。覆盖矩阵必须覆盖每项需求；引用只能来自本草案；声明已覆盖的用例必须已检查且关联该需求。
- 报告追加保存，不能覆盖旧报告。发布必须指定当前最新报告 ID，检查覆盖完整、无阻断项；警告或覆盖不足必须填写接受说明。发布生成内容与报告快照，不接受后续报告覆盖。
- MCP 不提供审批工具。网页审批属于本机单人工作流，不是能对抗同用户任意本地代码的权限隔离。

## 对外工具

get_platform_status、list_projects、get_project_context、list_skills、get_skill、get_submission_contract、list_dataset_drafts、submit_dataset_draft、get_dataset_draft、get_quality_report、submit_quality_report、list_dataset_versions、get_dataset_version。

工具返回真实服务器对象或明确错误。设置页显示可复制的启动配置、提交数据合同以及最近实际工具请求时间；不将“服务可用”表述为“外部客户端已连接”。

## 验收

本地独立 MCP 客户端完成工具发现、读取数据合同、提交草案、质量报告读取；网页能定位案例/需求证据、确认版本。自动测试使用独立数据库与明确标注的测试夹具。外部模型的质量判断能力需后续真实任务验证，本增量不声称已证明。
