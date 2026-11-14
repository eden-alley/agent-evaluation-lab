import React from "react";
import type { SkillDelivery, OutputChecks } from "../lib/skill-delivery";

export function ReviewMethod({
  delivery,
  checks,
  className,
}: {
  delivery?: SkillDelivery;
  checks?: OutputChecks;
  className?: string;
}) {
  if (!delivery)
    return (
      <details className={className}>
        <summary>方法提供记录 · 未记录</summary>
        <p>
          这份历史报告未记录方法正文的提供过程，不能据版本引用推断分析者已阅读。
        </p>
      </details>
    );
  const skill = delivery.skill;
  return (
    <details className={className}>
      <summary>
        本次 Skill ·{" "}
        {skill.method_version ? `v${skill.method_version}` : skill.name} ·
        已提供正文
      </summary>
      <p>
        {skill.name}
        。程序提供了以下固定正文；分析者阅读、模型遵循和语义正确性尚未验证。
      </p>
      <dl>
        <dt>Skill 版本</dt>
        <dd style={{ overflowWrap: "anywhere" }}>{skill.version_id}</dd>
        <dt>正文哈希</dt>
        <dd style={{ overflowWrap: "anywhere" }}>{skill.content_hash}</dd>
        <dt>提供记录</dt>
        <dd style={{ overflowWrap: "anywhere" }}>{delivery.id}</dd>
        <dt>提供时间与渠道</dt>
        <dd>
          {new Date(delivery.provided_at).toLocaleString("zh-CN")} ·{" "}
          {delivery.channel}
        </dd>
        <dt>明确指定讲解</dt>
        <dd>
          {delivery.requirements.explanation_case_ids.join("、") ||
            "无额外指定"}
        </dd>
        {delivery.requirements.explanation_policy === "key_cases" && (
          <>
            <dt>讲解方式</dt>
            <dd>
              按需选择退步、异常和建议依据中的关键题；建议引用题必须讲解。其他题由程序统计。
            </dd>
            <dt>程序提供的候选</dt>
            <dd>
              {delivery.key_case_candidates
                ?.map((c) => `${c.case_id}：${c.reasons.join("；")}`)
                .join("。") || "无"}
            </dd>
          </>
        )}
      </dl>
      <details>
        <summary>查看本次提供的 Skill 正文</summary>
        <pre
          style={{
            maxHeight: 340,
            overflow: "auto",
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
          }}
        >
          {skill.content}
        </pre>
      </details>
      {checks ? (
        <>
          <h3>输出检查 · 结构与引用通过</h3>
          <ul>
            {checks.checks.map((c) => (
              <li key={c.id}>
                {c.title}
                {c.case_ids?.length ? `：${c.case_ids.join("、")}` : ""}
                {c.evidence_count != null
                  ? `（${c.evidence_count}处依据）`
                  : ""}
              </li>
            ))}
          </ul>
          <p>{checks.scope}</p>
        </>
      ) : (
        <p>尚未记录本次输出检查。</p>
      )}
    </details>
  );
}
