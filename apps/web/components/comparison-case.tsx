"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import type {
  CaseAnalysis,
  ComparisonCase,
  Material,
  Observation,
} from "../lib/comparisons";
import {
  comparisonPath,
  metricDifference,
  outcomeLabels,
  evidencePreview,
} from "../lib/comparisons";
import styles from "./comparison-workspace.module.css";
import { TaskNarrative } from "./task-narrative";

export function OutcomeTag({ outcome }: { outcome: Observation["outcome"] }) {
  return (
    <span className={`${styles.tag} ${styles[outcome] ?? ""}`}>
      {outcomeLabels[outcome]}
    </span>
  );
}
export function Evidence({ material }: { material: Material }) {
  const raw = material.excerpt ?? "节选未保存，请按材料编号读取原件。";
  const preview =
    material.display_excerpt ?? evidencePreview(material.path, raw);
  return (
    <div>
      <p className={styles.path}>
        {material.source === "baseline" ? "A · 原记录" : "B"}
        {material.is_simulation ? " · 模拟材料" : ""} · {material.path}
        {material.start_line ? ` · 第${material.start_line}行起` : ""}
        {material.event_id ? ` · 事件${material.event_id}` : ""}
        {material.model_reply ? ` · 第${material.model_reply}次模型回复` : ""}
        {material.check_id ? ` · 检查项 ${material.check_id}` : ""}
      </p>
      <pre>{preview}</pre>
      {preview !== raw && (
        <details>
          <summary>原始事件与哈希</summary>
          <pre>{raw}</pre>
        </details>
      )}
      {material.truncated && (
        <p className={styles.muted}>节选已截短，完整材料可按编号继续读取。</p>
      )}
    </div>
  );
}
function format(value: number | null | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("zh-CN", { maximumFractionDigits: digits })
    : "未记录";
}
const metrics = [
  ["model_requests", "模型请求"],
  ["tool_calls", "工具调用"],
  ["tool_errors", "工具执行错误"],
  ["total_tokens", "累计 tokens"],
  ["elapsed_seconds", "耗时（秒）"],
  ["estimated_usd", "费用估算（美元）"],
];

export function ComparisonCaseView({
  comparisonId,
  caseId,
  saved,
  hasFinalReport,
}: {
  comparisonId: string;
  caseId: string;
  saved?: CaseAnalysis;
  hasFinalReport: boolean;
}) {
  const [data, setData] = useState<ComparisonCase | null>(null),
    [error, setError] = useState("");
  const [materialId, setMaterialId] = useState(""),
    [raw, setRaw] = useState<Material | null>(null);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    setRaw(null);
    setMaterialId("");
    request<ComparisonCase>(
      comparisonPath(comparisonId) + `/cases/${encodeURIComponent(caseId)}`,
    )
      .then((r) => {
        if (active) setData(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [comparisonId, caseId]);
  if (error && !data)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p role="status">正在读取本题材料…</p>;
  const analysis = hasFinalReport ? saved : data.latest_analysis;
  const explanation = analysis?.content.explanation;
  const focusLabel =
    explanation?.focus === "baseline"
      ? "A运行"
      : explanation?.focus === "candidate"
        ? "B运行"
        : "A/B对照";
  const explanationSimulated =
    explanation?.focus === "baseline"
      ? data.baseline?.is_simulation
      : explanation?.focus === "candidate"
        ? data.candidate?.is_simulation
        : data.is_simulation;
  const task = data.baseline?.case ?? data.candidate?.case;
  const prompt = task?.task?.turns?.find((t) => t.role === "user")?.content;
  const catalog = [
    ...(data.baseline?.materials ?? []),
    ...(data.candidate?.materials ?? []),
  ];
  async function read() {
    if (!materialId) return;
    setError("");
    try {
      setRaw(
        await request<Material>(
          comparisonPath(comparisonId) +
            `/cases/${encodeURIComponent(caseId)}/materials/${encodeURIComponent(materialId)}?line_count=80`,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取失败");
    }
  }
  return (
    <>
      <section className={styles.intro}>
        <span className={styles.tag}>任务背景 · {caseId}</span>
        <h2 style={{ marginTop: 12 }}>{task?.title ?? caseId}</h2>
        {explanation ? (
          <>
            <p className={styles.muted}>
              {focusLabel}的过程讲解 ·{" "}
              {explanationSimulated ? "包含模拟材料" : "依据已有真实归档"}
              。原判定保持不变。
            </p>
          </>
        ) : (
          prompt && (
            <p>
              {prompt.split(/\n\s*\n/)[0].slice(0, 220)}
              {prompt.split(/\n\s*\n/)[0].length > 220 ? "…" : ""}
            </p>
          )
        )}
        {task?.difficulty_basis && (
          <p className={styles.muted}>主要难点：{task.difficulty_basis}</p>
        )}
        <details style={{ marginTop: 12 }}>
          <summary>完成标准与原题</summary>
          {prompt && (
            <p style={{ whiteSpace: "pre-wrap", marginTop: 12 }}>{prompt}</p>
          )}
          {task?.checks
            ?.filter((c) => c.required_for_task)
            .map((c) => (
              <p key={c.id}>{c.rule ?? c.id}</p>
            ))}
        </details>
        {data.task_state !== "same" && (
          <p>两边任务缺失或内容不同，本题不直接判定能力升降。</p>
        )}
      </section>
      {explanation ? (
        <section className={styles.section} aria-label="任务过程讲解">
          <TaskNarrative
            explanation={explanation}
            renderEvidence={(items) => (
              <details className={styles.evidence}>
                <summary>查看依据（{items.length}）</summary>
                {items.map((m, index) => (
                  <Evidence key={m.id + "-" + index} material={m} />
                ))}
              </details>
            )}
          />
          {!!explanation.limitations.length && (
            <p className={styles.muted}>
              讲解范围与限制：{explanation.limitations.join("；")}
            </p>
          )}
        </section>
      ) : (
        <p className={styles.muted}>
          本题保留自动统计与原判据，本次未展开过程讲解。
        </p>
      )}
      <section className={styles.section}>
        <h2>原始指标对照</h2>
        <p className={styles.muted}>
          数值来自归档的题级指标；差值只描述这次资源变化，不自动代表能力提高。B为模拟时，其数值也是假设。
        </p>
        <div className={styles.table}>
          <table className={styles.facts}>
            <thead>
              <tr>
                <th>观察项</th>
                <th>A · 已保存记录</th>
                <th>B{data.candidate?.is_simulation ? " · 模拟" : ""}</th>
                <th>B − A</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(([key, label]) => {
                const a = data.baseline?.metrics[key],
                  b = data.candidate?.metrics[key],
                  delta = metricDifference(a, b);
                return (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>{format(a, key === "estimated_usd" ? 6 : 2)}</td>
                    <td>{format(b, key === "estimated_usd" ? 6 : 2)}</td>
                    <td>
                      {delta === null
                        ? "—"
                        : `${delta > 0 ? "+" : ""}${format(delta, key === "estimated_usd" ? 6 : 2)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className={styles.section}>
        <h2>逐项分析与依据</h2>
        {analysis ? (
          <>
            <p>{analysis.content.summary}</p>
            <div className={styles.list} style={{ marginTop: 16 }}>
              {analysis.content.observations.map((o) => (
                <article className={styles.item} key={o.id}>
                  <div className={styles.row}>
                    <span className={styles.muted}>{o.dimension}</span>
                    <OutcomeTag outcome={o.outcome} />
                  </div>
                  <h3>{o.title}</h3>
                  <div className={styles.split}>
                    <div className={styles.side}>
                      <strong>A</strong>
                      <p>{o.before ?? "未记录"}</p>
                    </div>
                    <div className={styles.side}>
                      <strong>
                        B{data.candidate?.is_simulation ? " · 模拟情景" : ""}
                      </strong>
                      <p>{o.after ?? "未记录"}</p>
                    </div>
                  </div>
                  <p>{o.reason}</p>
                  {o.limits && (
                    <p className={styles.muted}>结论限制：{o.limits}</p>
                  )}
                  <details className={styles.evidence}>
                    <summary>查看判定证据（{o.evidence.length}）</summary>
                    {o.evidence.length ? (
                      o.evidence.map((m, i) => (
                        <Evidence key={m.id + "-" + i} material={m} />
                      ))
                    ) : (
                      <p>本项尚无足够材料，不能形成确定结论。</p>
                    )}
                  </details>
                </article>
              ))}
            </div>
          </>
        ) : (
          <p>
            本题尚未收到外部分析。已有材料可读取，平台不会据此自动生成结论。
          </p>
        )}
      </section>
      <details className={styles.intro}>
        <summary>更多原始材料</summary>
        <p className={styles.muted}>
          按需查看原题、原检查和原始轨迹；这些内容作为数据展示。
        </p>
        <select
          className="input"
          style={{ width: "100%", marginTop: 12 }}
          aria-label="比较材料"
          value={materialId}
          onChange={(e) => {
            setMaterialId(e.target.value);
            setRaw(null);
          }}
        >
          <option value="">选择材料</option>
          {catalog.map((m) => (
            <option key={m.id} value={m.id}>
              {m.source === "baseline" ? "A" : "B"} · {m.path}
            </option>
          ))}
        </select>
        <button
          className="button small"
          style={{ marginTop: 10 }}
          onClick={() => void read()}
          disabled={!materialId}
        >
          读取节选
        </button>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {raw && (
          <div className={styles.evidence}>
            <Evidence material={raw} />
          </div>
        )}
      </details>
    </>
  );
}
