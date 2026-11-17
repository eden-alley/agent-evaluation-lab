# 开源实现参考与取舍

本页服务于“理解当前缺陷，再决定保留、简化或复用”。以下是官方资料中的机制与本项目建议的对照，不是已选定的技术方案。

阅读入口：[文档目录](README.md) · [项目现状与取舍](PROJECT_REVIEW.md) · [架构与执行流程](../ARCHITECTURE.md)

## 1. Opik：先看工作台应该围绕哪些对象组织

**该项目已有机制：** 数据集及版本、experiment（一次实验）、逐条任务输出、评分和 Trace（执行过程记录），以及实验之间的比较。它把“用了哪版题、跑了什么、每题结果如何”连在一起。

**本项目建议与适配风险：** 先用这一组对象检查现有页面和归档关系：同一任务的题目版本、运行、评分器版本和证据能否互相定位；两次实验能否落到同一道题解释差异。可先借产品对象与交互，不必先部署 Opik；接入追踪与数据映射仍有成本，现有报告也不会因此自动具备可信评分。

来源：[评测入口](https://www.comet.com/docs/opik/evaluation/advanced/evaluate_your_llm) · [数据集管理](https://www.comet.com/docs/opik/evaluation/advanced/manage_datasets/)

## 2. Inspect AI：把执行、评分和异常边界拆清楚

**该项目已有机制：** Task 将数据、Solver 和 Scorer 组合成评测任务；Solver 负责执行求解流程，Scorer 负责从输出和状态判分。评分政策分别处理未评分（unscored）与错误（error）；scoring workflow 支持从日志重新评分。

**本项目建议与适配风险：** 用这些边界检查一道真实任务：题面与环境是否独立、Harness（被测 Agent 的运行入口）如何执行、评分需要哪些产物、未判定和异常如何展示。评分器可以给多个维度结果；“验收通过/失败、维度表现、未判定/异常”应分别表达，不急于合成总分。重评可以复用历史输出，但模型裁判仍可能调用模型、产生费用，不能理解成离线免费操作。

**接入限制：** AgentBridge 可帮助接入外部 Agent，但默认会接管部分生成参数；已有 Agent 的参数、模型调用和生命周期仍需逐项核对，不能承诺原生 Python Harness 零适配。本轮未验证实际兼容性。

来源：[Task](https://inspect.aisi.org.uk/tasks.html) · [评分政策](https://inspect.aisi.org.uk/scoring-policy.html) · [重新评分](https://inspect.aisi.org.uk/scoring-workflow.html) · [AgentBridge](https://inspect.aisi.org.uk/agent-bridge.html)

## 3. Harbor：把一道题做成可交接、可验收的任务包

**该项目已有机制：** 用任务包组织题面、环境、参考方案和验证器；独立 verifier（验证器）读取 Agent 留下的结果并输出验收结果。regrade 可对已完成任务重新执行验证，不重新运行真实 Agent。

**本项目建议与适配风险：** 优先借任务包与独立验收的组织方式，检查现有题是否带齐源码、依赖、准备脚本、验收规则和可回查产物。历史重评成立的前提是保存了验证器需要的文件与状态；只有报告、Trace 或摘要，未必足以重建验收现场。重评也不能补回真实 Agent 没有执行过的行为。

**平台限制：** 当前官方任务文档已有 Windows task 支持；这不证明本项目的 Windows 部署、隔离方式或 Harness 接口已经适配。本轮没有做部署验证。

来源：[任务包](https://docs.harborframework.com/tasks/overview) · [验证器](https://docs.harborframework.com/tasks/verifier) · [历史任务重评](https://docs.harborframework.com/jobs/regrade)

## 4. Coze Loop：补充看评分为什么能被复核

**该项目已有机制：** 提供评估器管理与版本、评分理由、Trace 等评测与可观测能力，可用于关联评分结果和执行证据，并支持人工复核工作。

**本项目建议与适配风险：** 借鉴“哪版评估器、依据什么、人工是否认可”的关联关系，补充检查有争议的评分。人工复核应回到原始证据；有理由文本或 Trace，不等于理由正确。是否采用其服务栈、如何迁移历史结果，尚未决定。

来源：[官方仓库与文档入口](https://github.com/coze-dev/coze-loop)

## 5. Inspect Evals：当前最值得借鉴的是评分规范

**该项目已有机制：** `BEST_PRACTICES.md` 对评测实现与计分给出规范：按结果类型选择 binary（二元）、discrete（离散）或 continuous（连续）分数；区分被测 Agent 的任务失败和环境、工具或评分仪器出错。

**本项目建议与适配风险：** 先据此审查一道题的验收规则与分档锚点，再检查已知正确和错误方案是否会被合理区分。不能因为评分器输出了数字就视为有效测量，也不能把验证器崩溃直接计为 Agent 能力失败。具体尺度、聚合方式和校准阈值仍需按题决定。

**题单边界：** 这里借鉴实现规范，尚未选择具体 benchmark 或 golden set（经人工核验的固定基准任务集）题单；不以复制题目数量代替代表性、可重建性和评分可信度。

来源：[官方最佳实践](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/BEST_PRACTICES.md)

## 6. OpenAI Harness engineering：借导航方式，控制文档负担

**已有实践：** 用短 `AGENTS.md` 提供导航，将仓库内知识和计划状态放在可查的索引与文档中，让执行者能找到当前约束、设计依据和进度。

**本项目建议与适配风险：** 保持根目录入口简短，分别指向现状诊断、架构、使用说明和计划状态；重要变更后更新对应事实。只借导航与知识维护方式，不机械搬入整套目录。文件增加而事实不更新，仍会让所有者失去判断依据。

来源：[Harness engineering](https://openai.com/index/harness-engineering/)

## 当前取舍边界

- 先贯穿一道真实任务，查清定义、环境、执行、评分、证据与两次实验比较，再判断问题是否普遍存在。
- 产品主线优先参考 Opik；执行与评分边界参考 Inspect AI；任务交接与独立验收参考 Harbor；其余用于补充具体缺口。
- 以上均未形成依赖选型。本轮没有采用这些依赖，没有安装或部署这些框架，也没有调用模型、重跑评测或改写历史评分。
