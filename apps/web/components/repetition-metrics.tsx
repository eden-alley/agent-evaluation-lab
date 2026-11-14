import React from "react";
import type { RepetitionMetric } from "../lib/repetition";

const verdicts: Record<string, string> = {
  necessary: "必要重复",
  useless: "无效重复",
  insufficient: "证据不足",
};
export function RepetitionMetrics({
  metric,
  className,
}: {
  metric: RepetitionMetric;
  className?: string;
}) {
  const direction =
    (
      {
        improved: "本次进步",
        regressed: "本次退步",
        mixed: "有取舍",
        unchanged: "本次无明确变化",
      } as Record<string, string>
    )[metric.direction] ?? "证据不足";
  const rows = [
    ["工具调用", "total_calls"],
    ["原样重复候选", "candidate_count"],
    ["必要重复", "necessary"],
    ["确认无效（主指标）", "useless"],
    ["证据不足", "insufficient"],
  ] as const;
  const candidateCount = metric.cases.reduce(
    (n, c) =>
      n +
      (c.baseline?.candidate_count ?? 0) +
      (c.candidate?.candidate_count ?? 0),
    0,
  );
  return (
    <section className={className} aria-label={metric.name}>
      <h3>{metric.name}</h3>
      {!!metric.improved_cases?.length && (
        <p>改善题：{metric.improved_cases.join("、")}</p>
      )}
      {!!metric.regressed_cases?.length && (
        <p>退步题：{metric.regressed_cases.join("、")}</p>
      )}
      <p>
        确认无效次数：
        <strong>
          {metric.before ?? "—"} → {metric.after ?? "—"}
        </strong>{" "}
        · <strong data-direction={metric.direction}>{direction}</strong>
      </p>
      <p>{metric.definition}</p>
      <p>以下汇总仅包含 {metric.paired_cases} 道判定完整、可比较的题目。</p>
      <table>
        <thead>
          <tr>
            <th>观察项</th>
            <th>A</th>
            <th>B</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, key]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              <td>{metric.paired_cases ? metric.totals.baseline[key] : "—"}</td>
              <td>
                {metric.paired_cases ? metric.totals.candidate[key] : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        {metric.paired_cases}题可比
        {metric.excluded_cases.length
          ? `；未合并：${metric.excluded_cases.join("、")}`
          : ""}
        。跨工具等价重复：未评估。占比降低不自动代表能力进步。
      </p>
      {metric.cases.length > 1 && (
        <details>
          <summary>逐题总表（{metric.cases.length}题）</summary>
          <p>
            各列按 A → B
            排列。“确认无效”只列已确认次数；有待判候选或记录不完整时，不能把 0
            当作没有无效重复。
          </p>
          <div style={{ overflowX: "auto" }}>
            <table aria-label="原样重复逐题升降表">
              <thead>
                <tr>
                  <th>题目</th>
                  <th>确认无效</th>
                  <th>必要重复</th>
                  <th>证据不足候选</th>
                  <th>升降结论</th>
                </tr>
              </thead>
              <tbody>
                {metric.cases.map((row) => {
                  const a = row.baseline;
                  const b = row.candidate;
                  const direction =
                    !row.comparable || !a || !b
                      ? "insufficient"
                      : b.useless < a.useless
                        ? "improved"
                        : b.useless > a.useless
                          ? "regressed"
                          : "unchanged";
                  return (
                    <tr key={row.case_id}>
                      <th scope="row">{row.case_id}</th>
                      <td>
                        {a?.useless ?? "—"} → {b?.useless ?? "—"}
                      </td>
                      <td>
                        {a?.necessary ?? "—"} → {b?.necessary ?? "—"}
                      </td>
                      <td>
                        {a?.insufficient ?? "—"} → {b?.insufficient ?? "—"}
                      </td>
                      <td data-direction={direction}>
                        {direction === "insufficient"
                          ? "无法判断"
                          : direction === "improved"
                            ? "改善"
                            : direction === "regressed"
                              ? "退步"
                              : "持平"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <details>
        <summary>查看逐次判定与依据（{candidateCount}个原样重复候选）</summary>
        {metric.cases.map((row) => (
          <section key={row.case_id}>
            <h4>{row.case_id}</h4>
            <p>{row.reason}</p>
            {(["baseline", "candidate"] as const).map((side) => {
              const value = row[side];
              return (
                <div key={side}>
                  <h4>
                    {side === "baseline" ? "A" : "B"} 的判定 ·{" "}
                    {value?.status === "complete"
                      ? "满足当前单段统计条件"
                      : value
                        ? "不满足当前单段统计条件"
                        : "本历史对比未固定此项"}
                  </h4>
                  {value?.items.map((item) => (
                    <details key={item.event_id}>
                      <summary>
                        {side === "baseline" ? "A" : "B"} · 事件{item.event_id}
                        （前次{item.previous_event_id}）·{" "}
                        {verdicts[item.classification] ?? "证据不足"}
                      </summary>
                      <p>{item.reason}</p>
                      <pre>
                        {JSON.stringify(
                          { tool: item.tool, arguments: item.arguments },
                          null,
                          2,
                        )}
                      </pre>
                      {item.changed_files.length > 0 && (
                        <p>
                          两次调用之间变化的文件：
                          {item.changed_files.join("、")}
                        </p>
                      )}
                      {item.file_hashes && (
                        <details>
                          <summary>文件状态指纹</summary>
                          <pre>{JSON.stringify(item.file_hashes, null, 2)}</pre>
                        </details>
                      )}
                      {item.evidence.map((e, i) => (
                        <div key={i}>
                          <strong>{e.label}</strong>
                          <p>
                            {e.path} · 第{e.start_line}行 · 原件SHA-256{" "}
                            {e.sha256.slice(0, 12)}…
                          </p>
                          <pre>{e.excerpt}</pre>
                        </div>
                      ))}
                    </details>
                  ))}
                  {value?.candidate_count === 0 && (
                    <p>本范围未发现原样重复候选。</p>
                  )}
                </div>
              );
            })}
          </section>
        ))}
      </details>
      <p>
        判据版本：{metric.version}。程序只读分析执行过程，原任务评分保持不变。
      </p>
    </section>
  );
}
