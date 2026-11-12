import type { GradeValue } from "./judging";

export interface CheckerPackage { id: string; version: string; name: string; content_hash: string }
export interface CheckerBinding {
  id: string; created_at: string;
  snapshot: { task: { case_id: string; content_hash: string };
    package: CheckerPackage; environment: Record<string, string>; source_hash: string; input_hash: string };
}
export interface RecheckRow {
  id: string; rule: string; dimension: string; value: GradeValue; historical_value: GradeValue;
  reason: string; required_for_task: boolean; applicable: boolean; evidence: string[];
}
export interface CheckRun {
  id: string; binding_id: string; created_at: string; status: string;
  source_state?: string; source_warning?: string | null;
  error: { code: string; message: string } | null;
  report: { core_acceptance: string; checks: RecheckRow[];
    binding: CheckerBinding["snapshot"]; agent_model_requests: number; judge_model_requests: number;
    original_model_requests: number; seconds: number; provenance: string;
    evidence: { path: string; sha256: string; excerpt: string }[] } | null;
}
export interface CheckerContext {
  available: CheckerPackage[]; bindings: CheckerBinding[];
  runs: Pick<CheckRun, "id" | "binding_id" | "created_at" | "status">[];
}
export const statusLabel = (value: string) =>
  ({ queued: "等待检查", running: "正在检查", completed: "检查已完成", failed: "检查未完成" })[value] ?? value;
export function changedChecks<T extends { id: string; value: GradeValue; historical_value: GradeValue }>(checks: T[]) {
  return checks.filter(check => check.value !== check.historical_value);
}
