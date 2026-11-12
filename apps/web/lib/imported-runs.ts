export const dimensions = [
  "结果质量",
  "交付完整性与可用性",
  "实现与执行过程",
  "执行效率",
  "风险与约束遵守",
  "交付物可复现性",
];
export interface EvidenceFile {
  path: string;
  bytes: number;
  sha256: string;
}
export interface Check {
  id: string;
  dimension: string;
  value: number | "unknown";
  rule: string;
  reason: string;
  evidence: string;
  required_for_task: boolean;
  automatic_value?: number | "unknown";
}
export interface ImportedCase {
  id: string;
  title: string;
  group: string;
  difficulty_design: string;
  core_acceptance: string;
  checks: Check[];
  dimensions: Record<string, { P: number; F: number; U: number; N: number }>;
  metrics: {
    model_requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    elapsed_seconds: number;
    estimated_usd: string;
    stop_reasons: string[];
  };
  task: {
    turns: { index: number; role: string; content: string }[];
    source: unknown;
    controls: unknown;
    checks: unknown;
    difficulty_basis: string;
  };
  final_response: string;
  files: EvidenceFile[];
}
export interface ImportedRun {
  id: string;
  name: string;
  project_id: string;
  project_name: string;
  model: string;
  completed_at: string;
  case_count: number;
  counts: { pass: number; fail: number };
  requests: number;
  estimated_usd: string;
  prompt_tokens: number;
  completion_tokens: number;
  method: string;
  summary: string;
  dataset: {
    id: string;
    draft_id: string;
    name: string;
    version: number;
    content_hash: string;
  };
  cases: ImportedCase[];
  files: EvidenceFile[];
}
export function dimensionLabel(value?: {
  P: number;
  F: number;
  U: number;
  N: number;
}) {
  return !value || value.N === 0
    ? "—"
    : `${value.P} 满足 / ${value.F} 未满足 / ${value.U} 未知`;
}
export function artifactUrl(id: string, path: string, download = false) {
  return `/api/v1/evaluation-runs/${encodeURIComponent(id)}/artifact?${new URLSearchParams({ path, download: String(download) })}`;
}
