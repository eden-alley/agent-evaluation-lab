import type { Outcome } from "./comparisons";

export interface MetricEvidence {
  material_id: string;
  source: "baseline" | "candidate";
  path: string;
  sha256: string;
  start_line: number;
  line_count: number;
  check?: {
    id: string;
    value: unknown;
    rule?: string;
    reason?: string;
    evidence?: unknown;
  };
}
export interface MetricCase {
  case_id: string;
  before: number | null;
  after: number | null;
  comparable?: boolean;
  reason?: string;
  evidence: MetricEvidence[];
}
export interface CapabilityMetric {
  id: string;
  name: string;
  before: number | null;
  after: number | null;
  paired_cases: number;
  applicable_cases?: number;
  direction: Outcome | "increased" | "decreased";
  improved_cases?: string[];
  regressed_cases?: string[];
  case_evidence: MetricCase[];
  excluded: {
    case_id: string;
    reason: string;
    before?: number | null;
    after?: number | null;
  }[];
  definition?: string;
  unit?: string;
  relative_change_pct?: number | null;
}
export interface MetricReport {
  registry_version: string;
  quality: CapabilityMetric[];
  resources: CapabilityMetric[];
  unassessed: { id: string; name: string; reason: string }[];
  coverage: {
    quality_assessed: number;
    quality_total: number;
    resource_assessed: number;
    resource_total: number;
    unassessed: number;
  };
  conditions: {
    side: string;
    run_id?: string;
    model?: string;
    request_caps: string[];
  }[];
  limits: string[];
}

export function metricDirection(metric: CapabilityMetric) {
  const losses = metric.regressed_cases?.length,
    gains = metric.improved_cases?.length;
  switch (metric.direction) {
    case "improved":
      return losses ? "净进步 · 有回归" : "本次进步";
    case "regressed":
      return gains ? "净退步 · 有改善" : "本次退步";
    case "mixed":
      return "有取舍";
    case "unchanged":
      return "本次无明确变化";
    case "increased":
      return "计数上升";
    case "decreased":
      return "计数下降";
    default:
      return "无法判断";
  }
}

export function metricValue(value: number | null, denominator?: number) {
  if (value === null || denominator === 0) return "—";
  const text = value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  return denominator === undefined ? text : `${text} / ${denominator}`;
}

export function regressionFirst(metrics: CapabilityMetric[]) {
  const rank = (m: CapabilityMetric) =>
    m.direction === "regressed"
      ? 0
      : m.regressed_cases?.length
        ? 1
        : m.direction === "mixed"
          ? 2
          : m.direction === "insufficient"
            ? 3
            : 4;
  return [...metrics].sort((a, b) => rank(a) - rank(b));
}

export function evidenceOrder(metric: CapabilityMetric) {
  const rank = (r: MetricCase) =>
    r.comparable === false || r.before === null || r.after === null
      ? 3
      : r.after < r.before
        ? 0
        : r.after > r.before
          ? 1
          : 2;
  return [...metric.case_evidence].sort((a, b) =>
    metric.unit
      ? Math.abs((b.after ?? 0) - (b.before ?? 0)) -
        Math.abs((a.after ?? 0) - (a.before ?? 0))
      : rank(a) - rank(b),
  );
}
