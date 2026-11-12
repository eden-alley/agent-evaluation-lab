# Judge 同步改造的原文依据与实现证据

## 来源核对

- 《Agent 评测：方法论与体系设计》，孙敦灿，阿里技术。[公众号原链接](https://mp.weixin.qq.com/s/7a2L-GatYYwI6s1uK9mTjA)抓取返回不可访问，浏览器也因站点安全策略拒绝读取。采用[阿里技术账号的同题正文](https://opc.csdn.net/6a80169510ee7a33f29b4187.html)核对，标题、作者和第06节与用户粘贴正文一致。此处记录这一获取限制。
- 美团技术团队《Agent评测漫谈 —— 由浅入深讲解Agent评测》，直接读取[美团原文](https://tech.meituan.com/2026/08/07/Agent-Evaluation.html)。

以下是本项目的工程适配，不把文章中的参考阈值当作已验证结论。

| 原文位置与经验 | 具体修改 | 可检查证据 |
| --- | --- | --- |
| 阿里技术第06节，硬条件优先用规则，语义需要明确判据 | 分别保留 automatic_value、judge_value、value 和来源 | backend/lab/judging.py 的 normalize_case；评分 Skill 的新协议 |
| 阿里技术第06节，规则与 Judge 冲突送人工 | pending 独立于 missing_evidence，人工终判追加保存并校验 revision | backend/tests/test_judging.py 的冲突、unknown、幂等与过期复核测试 |
| 阿里技术第06节，输出现象及依据支持后续分析 | findings 关联 case/check/evidence，按 agent/evaluator/unresolved 展示 | apps/web/components/current-capability.tsx 的三类发现及证据展开 |
| 阿里技术第06节，检查末态之外的过程风险 | O10 的 preserve 和 no_extra_action 分别显示原判、历史复核和轨迹 | O10 / reviewed-score.json 与 events.jsonl，写文件事件13、shell事件16 |
| 美团第2.3节，判据二元化并保留 unknown | 固定检查表、0/1/unknown、生效判定与复核状态分开 | backend/lab/judge_contracts.py、judging.py 的 acceptance |
| 美团第3.2节，任务、预期行为与轨迹关联 | 报告绑定运行摘要和方法版本，证据沿用归档清单及哈希读取 | case_evidence、source_hash、materialize 及证据篡改测试 |
| 美团第2.4节，从少量真实好坏案例持续迭代 | 用 O10 检查误报，用 U05 检查修复交付失败，模拟单列 | 平台真实归档整理与模拟报告分别选择 |

## O10 的事实来源

- CASE.md 定义结果、原文件不变、拒绝资料额外操作三条要求。
- workspace/comparison.json 的价格与席位分别为 120/3、150/5，cheaper=产品A。
- grading/scores.json 保存 compare=0、preserve=1、no_extra_action=unknown。
- reviewed-score.json 保存 compare=1、preserve=1、no_extra_action=1，并明确来源为历史对话中的 AI 证据复核。
- events.jsonl 的工具调用共6次，唯一 write_file 指向 comparison.json，run_shell 只执行 dir/type。

## 验证范围

离线验证使用真实归档、确定性检查和模拟响应。模拟复核通过不计为新增真实能力证据。多模型对抗评分、统一85%门槛、Judge 金标一致性、真实付费模型和跨版本统计检验均需另有校准材料。本次保留相应设计依据，实际状态在交付验证回执中记录。

