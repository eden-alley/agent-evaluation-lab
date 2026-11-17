"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import { artifactUrl } from "../lib/imported-runs";

type Evidence = { path: string; line: number; event_id?: number; request_number?: number };
export type ArchiveBinding = { run_id: string; run_hash: string; manifest_hash: string };
export type RecoveryFacts = {
  truncations: { evidence: Evidence; completion_tokens: number | null; tools_executed: false | null }[];
  recovery: { status: "scheduled" | "response_complete" | "stopped"; reason?: string | null;
    mode?: "raise" | "split" | null; normal_cap?: number | null; recovery_cap?: number | null;
    request_cap?: number | null; evidence: Evidence }[];
  stop: { reason: string | null; text: string | null; evidence: Evidence } | null;
  task_success: null;
  limitations: string;
};
const reasons: Record<string, string> = {
  disabled: "未启用截断恢复", recovery_limit: "恢复次数已用完", output_truncated: "输出再次截断",
  usage_unknown: "用量未知，停止继续请求", token_limit: "达到 token 总额上限", time_limit: "达到总时长上限",
  max_steps: "达到最大步数", context_limit: "达到上下文限制", error: "执行报错",
  end_turn: "本轮回答结束；验收结论见评分区", verification_unmet: "验收未通过",
};

export function OutputRecoveryFacts({ runId, data }: { runId: string; data: RecoveryFacts }) {
  const evidence = (ref: Evidence) => (
    <a className="small" href={artifactUrl(runId, ref.path, true)}>
      原始记录 · 第 {ref.line} 行{ref.event_id !== undefined ? ` · 事件 ${ref.event_id}` : ""}
      {ref.request_number !== undefined ? ` · 请求 ${ref.request_number}` : ""}
    </a>
  );
  return (
    <>
      <p>{data.truncations.length ? `模型报告输出截断，找到 ${data.truncations.length} 条记录。` : "现有记录未确认输出截断。"}</p>
      {data.truncations.map((item, i) => (
        <p key={i}>
          {item.completion_tokens !== null ? `本次输出 ${item.completion_tokens.toLocaleString()} tokens。` : "本次输出用量未记录。"}
          {item.tools_executed === false ? " 本次工具调用均未执行。" : " 该响应中的工具执行情况未确认。"}{" "}
          {evidence(item.evidence)}
        </p>
      ))}
      {!data.recovery.length && <p>归档未记录恢复过程。</p>}
      {data.recovery.map((item, i) => (
        <p key={i}>
          {item.status === "scheduled" ? "准备继续，仍需通过请求前的预算检查。" :
            item.status === "response_complete" ? "收到完整响应；是否满足任务要求需看验收结果。" :
              `已停止恢复：${reasons[item.reason ?? ""] ?? item.reason ?? "原因未记录"}。`}{" "}
          {item.mode === "raise" ? "提高额度，重新生成完整响应。 " : item.mode === "split" ? "保持额度，尝试分步完成。 " : ""}
          {item.normal_cap != null && `正常上限 ${item.normal_cap} token。 `}
          {item.recovery_cap != null && `获准恢复上限 ${item.recovery_cap} token。 `}
          {item.request_cap != null && `本次上限 ${item.request_cap} token。 `}
          {evidence(item.evidence)}
        </p>
      ))}
      {data.stop && <details>
        <summary>最后停止记录：{reasons[data.stop.reason ?? ""] ?? data.stop.reason ?? "原因未记录"}</summary>
        <p style={{ whiteSpace: "pre-wrap" }}>{data.stop.text}</p>
        {evidence(data.stop.evidence)}
      </details>}
      <p className="small muted">{data.limitations}</p>
    </>
  );
}

export function OutputRecovery({ runId, caseId, binding, label = "输出与恢复" }: {
  runId: string; caseId: string; binding?: ArchiveBinding; label?: string;
}) {
  const [data, setData] = useState<RecoveryFacts | null>(null);
  const [error, setError] = useState("");
  const runHash = binding?.run_hash, manifestHash = binding?.manifest_hash;
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    const query = new URLSearchParams();
    if (runHash) query.set("expected_run_hash", runHash);
    if (manifestHash) query.set("expected_manifest_hash", manifestHash);
    request<RecoveryFacts>(`/evaluation-runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/output-recovery?${query}`)
      .then((value) => { if (active) setData(value); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "读取失败"); });
    return () => { active = false; };
  }, [runId, caseId, runHash, manifestHash]);
  return (
    <section className="panel pad section-bottom" aria-label={label}>
      <h3>{label}</h3>
      {error ? <p role="alert">{error}</p> : data ? <OutputRecoveryFacts runId={runId} data={data} /> :
        <p className="muted" role="status">正在核对输出与恢复记录…</p>}
    </section>
  );
}
