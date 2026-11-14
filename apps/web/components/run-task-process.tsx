"use client";
import React, { useEffect, useState } from "react";
import { request } from "../lib/api";
import type { ImportedCase } from "../lib/imported-runs";
import type { RunExplanation } from "../lib/run-explanations";
import type { Material } from "../lib/comparisons";
import { evidencePreview } from "../lib/comparisons";
import { TaskNarrative } from "./task-narrative";

type Introduction = { summary: string; acceptance?: string; detail?: string[] };

function Evidence({ items }: { items: Material[] }) {
  return (
    <details style={{ marginTop: 12 }}>
      <summary>查看依据（{items.length}）</summary>
      {items.map((ref, index) => (
        <div key={ref.id + index}>
          <p className="small muted">
            {ref.source === "baseline" ? "A" : "B"} · {ref.path}
            {ref.model_reply ? ` · 第${ref.model_reply}次模型回复` : ""}
            {ref.event_id
              ? ` · 事件${ref.event_id}`
              : ref.check_id
                ? ` · 检查项${ref.check_id}`
                : ` · 第${ref.start_line}行起`}
            {ref.is_simulation ? " · 模拟材料" : ""}
          </p>
          <pre className="code">
            {ref.display_excerpt ??
              evidencePreview(ref.path, ref.excerpt ?? "")}
          </pre>
          <details>
            <summary>原始节选与哈希</summary>
            <p className="small mono">{ref.sha256}</p>
            <pre className="code">{ref.excerpt}</pre>
          </details>
        </div>
      ))}
    </details>
  );
}

export function TaskProcessBody({
  item,
  data,
  introduction,
  loading,
  error,
  children,
}: {
  item: ImportedCase;
  data?: RunExplanation;
  introduction?: Introduction;
  loading?: boolean;
  error?: string;
  children?: React.ReactNode;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const explanation = data?.status === "available" ? data.explanation : null;
  const stops = item.metrics.stop_reasons ?? [];
  const stopLabels: Record<string, string> = {
    max_steps: "达到操作次数上限后停止",
    max_tokens: "达到 Token 上限后停止",
    timeout: "达到时间上限后停止",
    completed: "正常结束",
    final_response: "提交最终答复后结束",
  };
  return (
    <>
      <section className="panel pad" aria-label="任务过程">
        {explanation ? (
          <TaskNarrative
            explanation={explanation}
            renderEvidence={(items) => <Evidence items={items} />}
          />
        ) : (
          <>
            <h2>任务背景</h2>
            {introduction?.detail ? (
              introduction.detail.map((p) => <p key={p}>{p}</p>)
            ) : (
              <>
                <p>
                  {introduction?.summary ??
                    item.task.turns[0]?.content.split(/\n\s*\n/)[0]}
                </p>
                {introduction?.acceptance && (
                  <p>
                    <strong>怎样算完成：</strong>
                    {introduction.acceptance}
                  </p>
                )}
              </>
            )}
            <h2>本次结果</h2>
            <>
              <p>
                归档判定：
                {(
                  {
                    pass: "通过",
                    fail: "未通过",
                    unknown: "无法判定",
                  } as Record<string, string>
                )[item.core_acceptance] ?? item.core_acceptance}
                。
              </p>
              {item.checks
                .filter((c) => c.required_for_task && c.value !== 1)
                .map((c) => (
                  <p key={c.id}>{c.reason}</p>
                ))}
              {!!stops.length && (
                <p>
                  {stops
                    .map((s) => stopLabels[s] ?? `记录的停止原因：${s}`)
                    .join("；")}
                  。
                </p>
              )}
              <p className="small muted">
                当前为原任务与归档结果的自动摘要，本题未展开关键过程讲解。
              </p>
            </>
          </>
        )}
        {loading && (
          <p className="small muted" role="status">
            正在读取已保存的过程讲解…
          </p>
        )}
        {error && <p role="alert">保存的讲解暂时无法读取：{error}</p>}
        {data?.status === "source_changed" && (
          <p role="alert">
            原件已变化，未将历史讲解作为当前过程展示。请刷新运行记录，原始材料仍可核查。
          </p>
        )}
        {explanation && (
          <>
            {!!explanation.limitations.length && (
              <p className="small muted">
                讲解范围：{explanation.limitations.join("；")}
              </p>
            )}
            <details style={{ marginTop: 16 }}>
              <summary>讲解来源与范围</summary>
              <p>
                {explanation.focus === "comparison"
                  ? "A/B 对照讲解"
                  : explanation.focus === "baseline"
                    ? "A 运行讲解"
                    : "B 运行讲解"}
                {data?.source?.method_version
                  ? ` · Skill v${data.source.method_version}`
                  : ""}
                {data?.source?.analysis_origin === "offline_program"
                  ? " · 已有归档的离线整理"
                  : " · 已保存的分析报告"}
                。
              </p>
              {data?.source?.report_is_simulation && (
                <p>来源对比包含模拟材料，按上述 A/B 范围阅读。</p>
              )}
              <p className="small mono">报告：{data?.source?.report_id}</p>
              <p>
                讲解沿用保存时的结论，未修改原评分。字段和引用检查不代表原因假设已获证实。
              </p>
              {data?.source && (
                <a
                  className="button small"
                  href={`/comparison?comparison=${encodeURIComponent(data.source.comparison_id)}`}
                >
                  查看来源对比
                </a>
              )}
            </details>
          </>
        )}
      </section>
      <details
        className="panel pad"
        style={{ marginTop: 20 }}
        onToggle={(e) => setShowRaw(e.currentTarget.open)}
      >
        <summary>查看原始事件与交付文件</summary>
        {showRaw && children}
      </details>
    </>
  );
}

export function RunTaskProcess({
  runId,
  item,
  introduction,
  children,
}: {
  runId: string;
  item: ImportedCase;
  introduction?: Introduction;
  children?: React.ReactNode;
}) {
  const [data, setData] = useState<RunExplanation>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError("");
    setLoading(true);
    request<RunExplanation>(
      `/evaluation-runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(item.id)}/explanation`,
    )
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [runId, item.id]);
  return (
    <TaskProcessBody
      item={item}
      data={data}
      introduction={introduction}
      loading={loading}
      error={error}
    >
      {children}
    </TaskProcessBody>
  );
}
