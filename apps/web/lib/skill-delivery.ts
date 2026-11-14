export type ReviewScope = "focused" | "formal_batch";
export interface ReviewPolicy {
  mode: ReviewScope;
  label: string;
  case_count: number;
  recommendations_allowed: boolean;
}
export interface SkillDelivery {
  id: string;
  comparison_id: string;
  provided_at: string;
  channel: string;
  read_status: "not_verified";
  skill: {
    skill_id: string;
    version_id: string;
    content_hash: string;
    name: string;
    method_version: string | null;
    content: string;
  };
  requirements: {
    explanation_case_ids: string[];
    explanation_policy?: "key_cases";
    recommendations_allowed?: boolean;
  };
  review_policy?: ReviewPolicy;
  key_case_candidates?: { case_id: string; reasons: string[] }[];
  scope: string;
}
export interface OutputChecks {
  status: "passed";
  semantic_status: "not_evaluated";
  model_compliance: "not_verified";
  checks: {
    id: string;
    title: string;
    status: string;
    case_ids?: string[];
    evidence_count?: number;
  }[];
  scope: string;
}
