"use client";
import type { EvaluationRun } from "../lib/types";
import { summarizeRun } from "../lib/domain";
import { Badge as UiBadge } from "./ui/badge";
export const fmt = (value: number | null, suffix = "") =>
  value == null
    ? "—"
    : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + suffix;
export const json = (value: unknown) =>
  value == null
    ? "—"
    : typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);
export const status = (value: string) => {
  const labels: Record<string, string> = {
    completed: "已完成",
    error: "错误",
    timeout: "超时",
    running: "运行中",
    queued: "排队中",
    pass: "通过",
    fail: "未通过",
    pending_review: "待复核",
    ungraded: "未评分",
    scored: "已评分",
    missing_evidence: "证据不足",
    ok: "正常",
    regressed: "退化",
    fixed: "修复",
    unchanged: "未变化",
    modified: "内容变化",
    added: "新增",
    removed: "移除",
    incomparable: "不可比较",
  };
  return labels[value] || value;
};
const tone = (value: string) =>
  ["pass", "completed", "scored", "fixed", "ok"].includes(value)
    ? "good"
    : ["error", "timeout", "fail", "regressed"].includes(value)
      ? "bad"
      : ["pending_review", "ungraded", "missing_evidence"].includes(value)
        ? "warn"
        : "";
export function Badge({ value }: { value: string }) {
  return (
    <UiBadge
      variant={
        (tone(value) || "default") as
          "default" | "good" | "warn" | "bad" | "info"
      }
    >
      {status(value)}
    </UiBadge>
  );
}
export function Header({
  title,
  desc,
  action,
}: {
  title: string;
  desc: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      {action}
    </div>
  );
}
export function Tabs({
  labels,
  active,
  set,
}: {
  labels: string[];
  active: string;
  set: (v: string) => void;
}) {
  return (
    <div className="tabs">
      {labels.map((label) => (
        <button
          key={label}
          className={active === label ? "active" : ""}
          aria-pressed={active === label}
          onClick={() => set(label)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string | number;
  note?: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
export function RunMetrics({ run }: { run: EvaluationRun }) {
  const s = summarizeRun(run);
  return (
    <div className="metrics">
      <Metric label="数据集总数" value={run.total_dataset_cases} />
      <Metric label="已选择" value={s.selected} />
      <Metric
        label="执行已结束（含错误）"
        value={s.finished + "/" + s.selected}
      />
      <Metric label="已评分" value={s.scored + "/" + s.selected} />
      <Metric
        label="已评分用例通过率"
        value={s.pass_rate == null ? "—" : fmt(s.pass_rate * 100, "%")}
        note={"已评分 " + s.scored + "/" + s.selected}
      />
      <Metric
        label="平均耗时"
        value={fmt(s.average_latency_ms, " 毫秒")}
        note={"覆盖 " + s.latency_coverage + "/" + s.selected}
      />
      <Metric
        label="词元数 / 成本"
        value={
          s.total_tokens == null && s.total_cost == null
            ? "—"
            : fmt(s.total_tokens) + " / " + fmt(s.total_cost)
        }
        note={
          "覆盖 " +
          s.token_coverage +
          "/" +
          s.selected +
          " · " +
          s.cost_coverage +
          "/" +
          s.selected
        }
      />
    </div>
  );
}
