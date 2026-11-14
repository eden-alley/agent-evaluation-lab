import { request } from "./api";
import type { MetricReport } from "./capability-review";
import type {
  SkillDelivery,
  OutputChecks,
  ReviewPolicy,
  ReviewScope,
} from "./skill-delivery";
export type Outcome =
  | "improved"
  | "regressed"
  | "mixed"
  | "unchanged"
  | "insufficient"
  | "not_covered";
export const outcomeLabels: Record<Outcome, string> = {
  improved: "改善",
  regressed: "退步",
  mixed: "有取舍",
  unchanged: "无明确变化",
  insufficient: "证据不足",
  not_covered: "未覆盖",
};
export interface ObservationRef {
  case_id: string;
  observation_id: string;
}
export interface Material {
  id: string;
  source: "baseline" | "candidate";
  case_id: string;
  kind: string;
  path: string;
  sha256: string;
  bytes: number;
  excerpt?: string;
  start_line?: number;
  line_count?: number;
  is_simulation?: boolean;
  truncated?: boolean;
  display_excerpt?: string;
  event_id?: number;
  model_reply?: number;
  check_id?: string;
}
export interface CaseExplanation {
  case_id: string;
  focus: "baseline" | "candidate" | "comparison";
  background: string;
  stages: { title: string; text: string; evidence: Material[] }[];
  result: { text: string; evidence: Material[] };
  limitations: string[];
}
export interface Observation {
  id: string;
  dimension: string;
  title: string;
  outcome: Outcome;
  before: string | null;
  after: string | null;
  reason: string;
  limits: string;
  evidence: Material[];
}
export interface CaseAnalysis {
  id: string;
  case_id: string;
  revision: number;
  created_at: string;
  content: {
    summary: string;
    observations: Observation[];
    explanation?: CaseExplanation;
  };
}
export interface Analyst {
  kind: string;
  name?: string;
  model?: string | null;
}
export interface Source {
  name: string;
  model?: string | null;
  run_id?: string;
  fixture_id?: string;
  is_simulation: boolean;
}
export interface Progress {
  planned: number;
  received: number;
  collection_complete: boolean;
  observations: number;
  assessed: number;
  unknown: number;
  not_covered: number;
}
export interface Finding {
  title: string;
  outcome: Outcome;
  explanation: string;
  refs: ObservationRef[];
}
export interface Recommendation {
  title: string;
  phenomenon: string;
  cause_status: string;
  cause: string;
  action: string;
  priority_reason: string;
  validation: string;
  success_signals: string;
  guardrails: string;
  refs: ObservationRef[];
  known_mechanism?: string;
  gap?: string;
  evidence?: Material[];
}
export interface ComparisonReport {
  id: string;
  created_at: string;
  report_hash: string;
  source_state: string;
  source_checked_at: string | null;
  source_state_scope: "last_full_verification";
  is_simulation: boolean;
  analyst: Analyst;
  summary: string;
  case_report_ids: string[];
  case_analyses: CaseAnalysis[];
  findings: Finding[];
  recommendations: Recommendation[];
  progress: Progress;
  validation_scope: string;
  metric_report?: MetricReport;
  analysis_origin?: {
    kind: string;
    model_calls: number | null;
    statistics: string;
    advice: string;
  };
  workflow?: Comparison["workflow"];
  skill_delivery?: SkillDelivery;
  output_checks?: OutputChecks;
  no_recommendation_reason?: string | null;
  review_policy?: ReviewPolicy;
  explanation_coverage?: {
    provided: number;
    planned: number;
    case_ids: string[];
    mode?: "key_cases";
    total_cases?: number;
    candidate_case_ids?: string[];
    not_explained_case_ids?: string[];
    unexpanded_candidate_case_ids?: string[];
  };
}
export function reviewScopeFor(
  caseCount: number,
  requested: ReviewScope = "focused",
): ReviewScope {
  return caseCount > 3 ? requested : "focused";
}
export function developmentAdvice(
  report: ComparisonReport | null,
): Recommendation[] {
  return report?.review_policy?.recommendations_allowed === false
    ? []
    : (report?.recommendations ?? []);
}
export interface Comparison {
  id: string;
  name: string;
  objective: string;
  created_at: string;
  project_id: string;
  state: string;
  is_simulation: boolean;
  analyst: Analyst;
  baseline: Source;
  candidate: Source | null;
  workflow: { skill_id: string; version_id: string; content_hash: string };
  source_state: string;
  source_checked_at: string | null;
  source_state_scope: "last_full_verification";
  progress: Progress;
  queue: {
    case_id: string;
    title: string;
    task_state: string;
    analysis_id: string | null;
    revision: number;
  }[];
  reports: { id: string; created_at: string }[];
  latest_report: ComparisonReport | null;
  has_unreported_changes: boolean;
}
export interface CaseSide {
  case: {
    id: string;
    title: string;
    difficulty_basis?: string;
    task?: { turns?: { role: string; content: string }[] };
    checks?: {
      id: string;
      rule?: string;
      required_for_task?: boolean;
      value: unknown;
    }[];
  };
  metrics: Record<string, number | null>;
  materials: Material[];
  is_simulation: boolean;
}
export interface ComparisonCase {
  case_id: string;
  task_state: string;
  source_state: string;
  source_checked_at: string | null;
  source_state_scope: "last_full_verification";
  baseline: CaseSide | null;
  candidate: CaseSide | null;
  latest_analysis: CaseAnalysis | null;
  is_simulation: boolean;
}
export function metricDifference(
  before: unknown,
  after: unknown,
): number | null {
  return typeof before === "number" &&
    typeof after === "number" &&
    Number.isFinite(before) &&
    Number.isFinite(after)
    ? after - before
    : null;
}
export function affectedCases(refs: ObservationRef[]): number {
  return new Set(refs.map((ref) => ref.case_id)).size;
}
export function demonstration(value: {
  is_simulation: boolean;
  analyst: Analyst;
}): boolean {
  return value.is_simulation || value.analyst.kind === "offline_fixture";
}
export const comparisonPath = (id: string) =>
  `/comparisons/${encodeURIComponent(id)}`;

export function evidencePreview(path: string, raw: string): string {
  if (!path.endsWith("events.jsonl")) return raw;
  try {
    const events = raw
      .split(/\r?\n/)
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line));
    if (
      !events.length ||
      events.some((event) => !event || typeof event !== "object" || !event.type)
    )
      return raw;
    return events
      .map((event) => {
        const heading = [
          `事件 ${event.event_id ?? "?"}`,
          event.type,
          event.tool,
          event.exit_code != null ? `exit_code=${event.exit_code}` : null,
        ]
          .filter(Boolean)
          .join(" · ");
        const body = [
          event.message,
          event.data,
          event.text,
          event.stop_reason ? `停止原因：${event.stop_reason}` : null,
        ]
          .filter((value) => value != null)
          .map((value) =>
            typeof value === "string" ? value : JSON.stringify(value, null, 2),
          );
        return [heading, ...body].join("\n");
      })
      .join("\n\n");
  } catch {
    return raw;
  }
}

export interface SourceVerification {
  source_state: string;
  source_checked_at: string | null;
  source_state_scope?: "last_full_verification";
}
export async function loadComparisonView(
  id: string,
  get: typeof request = request,
) {
  return id
    ? { detail: await get<Comparison>(comparisonPath(id)), items: null }
    : {
        detail: null,
        items: (await get<{ items: Comparison[] }>("/comparisons")).items,
      };
}
export function sourceVerificationText(source: SourceVerification): string {
  if (!source.source_checked_at) return "最近完整校验：未记录";
  const date = new Date(source.source_checked_at);
  const time = Number.isNaN(date.getTime())
    ? source.source_checked_at
    : date.toLocaleString("zh-CN");
  const state =
    source.source_state === "unchanged"
      ? "未变化"
      : source.source_state === "changed"
        ? "已变化"
        : "未核验";
  return `最近完整校验：${time} · ${state}`;
}
export function createEvidenceVerifier(
  id: string,
  send: typeof request = request,
) {
  let pending: Promise<SourceVerification> | null = null;
  return () => {
    if (!pending)
      pending = send<SourceVerification>(`${comparisonPath(id)}/verify`, {
        method: "POST",
      }).finally(() => {
        pending = null;
      });
    return pending;
  };
}
