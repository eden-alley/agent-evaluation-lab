export type Verdict = "pass" | "fail" | "pending_review" | "ungraded";
export type ExecutionStatus =
  "completed" | "error" | "timeout" | "running" | "queued";
export interface DatasetCase {
  case_id: string;
  title: string;
  input: Record<string, unknown>;
  expected: Record<string, unknown> | null;
  categories: string[];
  content_hash: string;
}
export interface Dataset {
  id: string;
  name: string;
  version: number;
  description: string;
  cases: DatasetCase[];
}
export interface RubricDimension {
  id: string;
  name: string;
  description: string;
  version: number;
  method: "code" | "human" | "llm";
  weight: number | null;
  hard_failure: boolean;
  required_evidence: string[];
}
export interface Rubric {
  id: string;
  name: string;
  version: number;
  dimensions: RubricDimension[];
}
export interface TraceSpan {
  id: string;
  parent_id: string | null;
  name: string;
  type: "agent" | "llm" | "tool";
  status: "ok" | "error";
  started_at: string;
  duration_ms: number | null;
  input: unknown;
  output: unknown;
  error: string | null;
}
export interface Grade {
  dimension_id: string;
  name: string;
  status: "scored" | "pending_review" | "missing_evidence" | "error";
  score: number | null;
  reason: string;
  evidence_span_ids: string[];
}
export interface Trial {
  id: string;
  case_id: string;
  title: string;
  category: string;
  case_hash: string;
  execution_status: ExecutionStatus;
  verdict: Verdict;
  latency_ms: number | null;
  tokens: number | null;
  cost: number | null;
  output: string | null;
  error: string | null;
  trace_id: string;
  spans: TraceSpan[];
  grades: Grade[];
}
export interface EvaluationRun {
  id: string;
  name: string;
  origin: "fixture";
  agent_name: string;
  agent_version: string;
  dataset_id: string;
  dataset_version: number;
  rubric_id: string;
  rubric_version: number;
  total_dataset_cases: number;
  created_at: string;
  status: "completed" | "running";
  trials: Trial[];
}
export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}
export interface AvailabilityReport {
  configuration_status: "ready" | "unavailable";
  runtime_status: "not_tested";
  checked_at: string;
  checks: { name: string; status: "pass" | "fail"; message: string }[];
  git_commit: string | null;
  git_dirty: boolean | null;
}
export interface AgentRegistration {
  id: string;
  project_id: string;
  name: string;
  source_path: string;
  python_executable: string;
  entrypoint: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_check: AvailabilityReport | null;
}
export interface Health {
  status: "ok";
  database: "sqlite";
  journal_mode: "wal";
  capabilities: {
    projects: boolean;
    agent_registration: boolean;
    agent_check: boolean;
    evaluation_execution: boolean;
    dataset_quality_handoff: boolean;
    external_agent_tools: boolean;
    skill_catalog: boolean;
  };
}
export interface RunSummary {
  selected: number;
  finished: number;
  scored: number;
  passed: number;
  failed: number;
  pending: number;
  execution_errors: number;
  execution_coverage: number | null;
  grading_coverage: number | null;
  pass_rate: number | null;
  average_latency_ms: number | null;
  latency_coverage: number;
  total_tokens: number | null;
  token_coverage: number;
  total_cost: number | null;
  cost_coverage: number;
}
export interface DimensionSummary {
  id: string;
  name: string;
  mean: number | null;
  scored: number;
  selected: number;
}
export interface ComparisonRow {
  case_id: string;
  title: string;
  baseline: Trial | null;
  candidate: Trial | null;
  change:
    | "regressed"
    | "fixed"
    | "unchanged"
    | "ungraded"
    | "modified"
    | "added"
    | "removed"
    | "incomparable";
}
export interface Comparison {
  comparable: boolean;
  reason: string | null;
  rows: ComparisonRow[];
  regressions: number;
  fixes: number;
}
export interface JsonlValidation {
  valid: boolean;
  cases: DatasetCase[];
  errors: { line: number; message: string }[];
  categories: string[];
}
