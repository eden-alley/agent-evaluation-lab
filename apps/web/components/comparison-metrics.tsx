"use client";
import { useEffect, useRef, useState } from "react";
import type { CapabilityMetric, MetricReport } from "../lib/capability-review";
import {
  metricDirection,
  metricValue,
  regressionFirst,
  evidenceOrder,
} from "../lib/capability-review";
import styles from "./comparison-metrics.module.css";

export function ComparisonMetrics({
  report,
  openCase,
}: {
  report: MetricReport;
  openCase: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const evidencePanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selected) {
      evidencePanel.current?.focus({ preventScroll: true });
      evidencePanel.current?.scrollIntoView({ block: "nearest" });
    }
  }, [selected]);
  const metric = [...report.quality, ...report.resources].find(
    (m) => m.id === selected,
  );
  function evidenceButton(m: CapabilityMetric) {
    return (
      <button
        className={styles.metricButton}
        aria-expanded={selected === m.id}
        aria-controls="metric-evidence"
        onClick={() => setSelected(selected === m.id ? null : m.id)}
      >
        {m.name}
      </button>
    );
  }
  return (
    <div className={styles.root}>
      <section aria-labelledby="quality-metrics">
        <h2 id="quality-metrics">指标升降表</h2>
        <p className={styles.caption}>
          已统计 {report.coverage.quality_assessed} /{" "}
          {report.coverage.quality_total} 项质量指标、
          {report.coverage.resource_assessed} 项资源指标；另有{" "}
          {report.coverage.unassessed} 个方向未评估。点击指标查看题目和判据。
        </p>
        <div
          className={styles.scroll}
          tabIndex={0}
          role="region"
          aria-label="质量指标升降"
        >
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">质量与行为</th>
                <th scope="col">A</th>
                <th scope="col">B</th>
                <th scope="col">本次变化</th>
              </tr>
            </thead>
            <tbody>
              {regressionFirst(report.quality).map((m) => (
                <tr key={m.id}>
                  <th scope="row">
                    {evidenceButton(m)}
                    <small>
                      {m.paired_cases} 题可比
                      {m.excluded.length
                        ? ` · ${m.excluded.length} 题存疑`
                        : ""}
                    </small>
                  </th>
                  <td className={styles.numeric}>
                    {metricValue(m.before, m.paired_cases)}
                  </td>
                  <td className={styles.numeric}>
                    {metricValue(m.after, m.paired_cases)}
                  </td>
                  <td>
                    <strong
                      className={
                        m.direction === "regressed"
                          ? styles.regressed
                          : m.direction === "improved"
                            ? styles.improved
                            : styles.neutral
                      }
                    >
                      {metricDirection(m)}
                    </strong>
                    {!!m.improved_cases?.length && (
                      <small>改善：{m.improved_cases.join("、")}</small>
                    )}
                    {!!m.regressed_cases?.length && (
                      <small className={styles.regressed}>
                        回归：{m.regressed_cases.join("、")}
                      </small>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.caption}>
          数字为通过题数 / 同题同判据的共同题数；各项分母不同，不合成总分。
        </p>
      </section>
      {metric && (
        <section
          id="metric-evidence"
          ref={evidencePanel}
          tabIndex={-1}
          className={styles.evidence}
          aria-label={metric.name + "的依据"}
        >
          <div className={styles.evidenceHeading}>
            <h3>{metric.name}：根据哪些题判断</h3>
            <button className="button small" onClick={() => setSelected(null)}>
              收起依据
            </button>
          </div>
          <p>
            {metric.definition ?? "保存的资源与事件计数，只描述本次消耗变化。"}
          </p>
          {evidenceOrder(metric).map((row) => (
            <details className={styles.case} key={row.case_id}>
              <summary>
                {row.case_id} · A {metricValue(row.before)} → B{" "}
                {metricValue(row.after)}
                {row.comparable === false
                  ? " · 未计入分母"
                  : row.after !== null &&
                      row.before !== null &&
                      row.after < row.before &&
                      !metric.unit
                    ? " · 退步"
                    : ""}
              </summary>
              <p>{row.reason}</p>
              <div className={styles.sides}>
                {(["baseline", "candidate"] as const).map((side) => (
                  <div key={side}>
                    <h4>{side === "baseline" ? "A 的证据" : "B 的证据"}</h4>
                    {row.evidence
                      .filter((e) => e.source === side)
                      .map((e, i) => (
                        <div key={i} className={styles.check}>
                          {e.check ? (
                            <>
                              <strong>
                                {e.check.id} = {String(e.check.value)}
                              </strong>
                              <p>{e.check.rule}</p>
                              <p>{e.check.reason}</p>
                              {e.check.evidence != null && (
                                <pre>
                                  {typeof e.check.evidence === "string"
                                    ? e.check.evidence
                                    : JSON.stringify(e.check.evidence)}
                                </pre>
                              )}
                            </>
                          ) : (
                            <p>
                              归档值：
                              {metricValue(
                                side === "baseline" ? row.before : row.after,
                              )}
                            </p>
                          )}
                          <small>
                            {e.path} · 第 {e.start_line} 行起
                          </small>
                        </div>
                      ))}
                  </div>
                ))}
              </div>
              <button
                className="button small"
                onClick={() => openCase(row.case_id)}
              >
                查看 {row.case_id} 任务与完整证据
              </button>
            </details>
          ))}
          {!!metric.excluded.length && (
            <p className={styles.caption}>
              未计入：
              {metric.excluded
                .map((e) => `${e.case_id}（${e.reason}）`)
                .join("；")}
            </p>
          )}
        </section>
      )}
      <section aria-labelledby="resource-metrics">
        <h2 id="resource-metrics">资源与执行计数</h2>
        <p className={styles.caption}>
          消耗增减单独观察；更多调用也可能来自更完整的工作。
        </p>
        <div
          className={styles.scroll}
          tabIndex={0}
          role="region"
          aria-label="资源变化"
        >
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">记录项</th>
                <th scope="col">A</th>
                <th scope="col">B</th>
                <th scope="col">变化</th>
              </tr>
            </thead>
            <tbody>
              {report.resources.map((m) => (
                <tr key={m.id}>
                  <th scope="row">
                    {evidenceButton(m)}
                    <small>
                      {m.paired_cases} 题 · {m.unit}
                    </small>
                  </th>
                  <td className={styles.numeric}>{metricValue(m.before)}</td>
                  <td className={styles.numeric}>{metricValue(m.after)}</td>
                  <td className={styles.numeric}>
                    {m.relative_change_pct == null
                      ? metricDirection(m)
                      : `${m.relative_change_pct > 0 ? "+" : ""}${m.relative_change_pct.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-labelledby="unassessed-metrics">
        <h2 id="unassessed-metrics">目前还不能判断的能力</h2>
        <div className={styles.unknowns}>
          {report.unassessed.map((m) => (
            <div key={m.id}>
              <strong>{m.name}</strong>
              <span>未评估</span>
              <p>{m.reason}</p>
            </div>
          ))}
        </div>
      </section>
      <details className={styles.limits}>
        <summary>比较条件与统计口径</summary>
        {report.conditions.map((c) => (
          <p key={c.side}>
            {c.side === "baseline" ? "A" : "B"}：{c.run_id ?? "模拟来源"}
            ；请求上限 {c.request_caps.join("、") || "未记录"}
          </p>
        ))}
        <ul>
          {report.limits.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
        <p>统计口径：{report.registry_version}。原评分保持不变。</p>
      </details>
    </div>
  );
}
