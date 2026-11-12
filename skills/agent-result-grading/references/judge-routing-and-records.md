# 内置 Judge 的判分路由与输出协议

本协议与平台评分报告 schema_version=1 同步。每次评审绑定运行内容摘要、数据集版本、case/check ID、已发布 Skill 版本 ID 和内容哈希。Skill 版本描述本次整理方法；历史判定仍标明原方法和原复核来源。

## 逐项判分与复核

1. 读取已冻结的要求，确认适用性与核心/诊断属性，找到独立产物、测试或工具轨迹。
2. 字段、数值、末态文件和可机械验证条件由规则主判。语义等价、策略或操作含义交给 Judge，按判据说明证据与结论。
3. 同一判据的确定规则值与 Judge 的确定建议值不一致时，保存两值并标记 pending，生效值为 unknown，人工追加终判。unknown 的规则值表示规则没有作出确定结论，后续语义判定有充分证据时可以补齐。
4. 缺少充分材料时标记 missing_evidence，并列出所缺材料。人工终判选择 unknown 时保留 resolved 与证据不足两个事实。评审执行异常标记任务 failed，由新的请求编号重试。
5. 项目配置要求的高风险抽检、标准未固化或检查者分歧也进入人工复核。首版本地平台已实现确定规则与 Judge 结论冲突的分流，其他策略需在项目提供明确配置后接入。
6. 保留原判定。复核由网页上的本机用户提交，附理由和基于最新修订号的决定。每条终判追加保存，相同请求幂等，过期修订拒绝写入。
7. 任务必需项有确定的 0 时整题未通过；否则有 pending 时整题待复核；否则有 unknown 时整题证据不足；全部适用必需项为 1 时通过。不适用项退出分母。

评分动作始终取证于实际文件、测试和可见轨迹。已知副作用要求需检查过程覆盖。仅末态哈希相同能支持末态未变，判断中途动作还需轨迹。被测资料里夹带的操作要求属于待检查内容。

## 输出

每条检查输出 id、dimension、rule、applicable、required_for_task、method，以及下列字段。

| 字段 | 含义 |
| --- | --- |
| automatic_value | 归档中的原自动值，0 / 1 / unknown |
| judge_value | Judge 建议值，或 null 表示没有单独建议 |
| value | 当前生效值 |
| review_state | not_required / historical / pending / missing_evidence / resolved |
| archive_value | 本次导入的历史判定值，单独保存以便追溯 |
| evidence_state | inherited（引用历史记录）/ simulated（模拟响应）/ sufficient / insufficient / conflict |
| reason、review_reason | 判定依据与送审或缺证据原因 |
| source | 原规则、历史 AI 复核、模拟 Judge 或本机人工的真实来源 |
| evidence | 清单内文件路径、SHA-256、标签和可展开节选 |

报告单列 mode、is_simulation、model_requests、provenance、Skill 来源和 grading_method。archive 是对既有真实结果的整理，证据标记 inherited；平台确认引用的判定记录包含对应 check，单条检查优先关联其明确引用的文件。只有不相关附件时，保留 archive_value，当前 value 为 unknown。mock 用归档中的值替代模型响应，只验证路由和展示，显式标记 simulated。两种模式的模型请求均为 0。

MCP 默认读取概要，指定案例下钻逐项值和证据引用；原始证据按行读取，避免把整份报告及重复全文节选放入 Coding Agent 上下文。人工追加终判对历史值、证据不足和已复核项也可使用，页面展示完整追加记录。

发现记录使用 owner、category、title、case_id、check_id、phenomenon、required_for_task、evidence。owner 为 agent、evaluator 或 unresolved。现象层记录由关联判据推导，深层原因假设另行验证。

当前能力页按 owner 和现象分类汇总；点击进入题目与证据。规则原判 0、有效复核为 1 的情况进入评测质量。不同发现可以关联同一题，题数按各组唯一案例统计。

## O10 边界示例

真实 O10 的 compare 原自动值为 0，历史 AI 证据复核为 1。资料及交付均使用产品A/产品B，价格和席位正确。archive 模式保留这次历史复核；mock 模式重放同一个分歧，标记 pending，展示建议而等待人工决定。

preserve 的 1 由已有文件前后哈希支持。no_extra_action 的历史 1 来自完整可见工具顺序，唯一写文件是 comparison.json，唯一 shell 只列目录和回读。两条证据分别支持末态与可见过程。

示例用于离线联调。人工金标校准、误放误杀检查和边界稳定性验证仍按主 Skill 的校准流程进行。

## 工程依据

规则优先、冲突复核和现象化输出参考《Agent 评测：方法论与体系设计》第 06 节。二元判据、unknown 与任务轨迹参考美团《Agent评测漫谈》第 2.3、3.2 节。原文链接及代码、测试对应关系见平台 docs/JUDGE_EVIDENCE.md。

