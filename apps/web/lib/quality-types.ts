export interface SkillReference {
  skill_id: string;
  version_id: string;
  content_hash: string;
}
export interface Source {
  client: string;
  skill_name?: string | null;
  skill_version?: string | null;
  skills: SkillReference[];
}
export interface Requirement {
  id: string;
  description: string;
}
export interface QualityCase {
  case_id: string;
  title: string;
  input: Record<string, unknown>;
  expected: Record<string, unknown> | null;
  categories: string[];
  requirement_ids: string[];
  grading_notes: string;
}
export interface DraftPayload {
  project_id: string;
  name: string;
  task_description: string;
  requirements: Requirement[];
  cases: QualityCase[];
  source: Source;
  base_version_id: string | null;
  request_id: string;
}
export interface Check {
  id: string;
  category: string;
  severity: "blocker" | "warning" | "info";
  case_ids: string[];
  requirement_ids: string[];
  message: string;
  origin: "deterministic";
}
export interface EvidenceRef {
  target_type: "case" | "requirement" | "task";
  target_id: string | null;
  field: string;
  quote: string;
}
export interface Finding {
  id: string;
  severity: "blocker" | "warning" | "info";
  category: string;
  case_ids: string[];
  requirement_ids: string[];
  evidence: EvidenceRef[];
  explanation: string;
  suggestion: string;
}
export interface Coverage {
  requirement_id: string;
  status: "covered" | "partial" | "missing" | "not_assessed";
  case_ids: string[];
  reason: string;
}
export interface QualityReport {
  id: string;
  draft_id: string;
  sequence: number;
  created_at: string;
  payload: {
    request_id: string;
    draft_hash: string;
    source: Source;
    summary: string;
    reviewed_case_ids: string[];
    coverage: Coverage[];
    findings: Finding[];
  };
}
export interface QualityMetrics {
  total_cases: number;
  requirements: number;
  structurally_checked_cases: number;
  reviewed_cases: number;
  covered_requirements: number;
  blockers: number;
  warnings: number;
}
export interface ReviewDecision {
  decision: "approve" | "reject";
  report_id: string | null;
  note: string;
  decided_at: string;
}
export interface DraftSummary {
  id: string;
  project_id: string;
  dataset_id: string;
  name: string;
  content_hash: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  source: Source;
  base_version_id: string | null;
  metrics: QualityMetrics;
}
export interface DatasetDraft extends Omit<DraftSummary, "name" | "source"> {
  payload: DraftPayload;
  checks: Check[];
  latest_report: QualityReport | null;
  report_history: { id: string; sequence: number; created_at: string }[];
  decision: ReviewDecision | null;
}
export interface VersionSummary {
  id: string;
  dataset_id: string;
  draft_id: string;
  name: string;
  version: number;
  content_hash: string;
  created_at: string;
  case_count: number;
}
export interface DatasetVersion {
  id: string;
  project_id: string;
  dataset_id: string;
  draft_id: string;
  version: number;
  content_hash: string;
  payload: DraftPayload;
  checks: Check[];
  quality_report: QualityReport;
  decision: ReviewDecision;
  created_at: string;
}
export interface SkillVersion {
  id: string;
  skill_id: string;
  version: number;
  content: string;
  content_hash: string;
  change_note: string;
  status: "draft" | "published";
  created_at: string;
  published_at: string | null;
}
export interface Skill {
  id: string;
  name: string;
  description: string;
  kind: "evaluation" | "business";
  tags: string[];
  origin: "builtin" | "user";
  active_version_id: string | null;
  created_at: string;
  active_version: Pick<
    SkillVersion,
    "id" | "version" | "content_hash" | "published_at"
  > | null;
  versions?: SkillVersion[];
}
export interface Integration {
  transport: string;
  protocol: string;
  tool_names: string[];
  startup: { command: string; args: string[]; env: Record<string, string> };
  last_call: {
    client: string;
    tool: string;
    status_code: number;
    created_at: string;
  } | null;
  recorded_calls: number;
  skill_policy: string;
}
