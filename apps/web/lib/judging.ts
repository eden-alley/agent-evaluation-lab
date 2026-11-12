import type { EvidenceFile } from "./imported-runs";

export type GradeValue = 0 | 1 | "unknown";
export type JudgeEvidence = Pick<EvidenceFile, "path" | "sha256"> & {
  label: string; excerpt: string; truncated: boolean;
};
export interface JudgeCheck {
  id: string; rule: string; dimension: string;
  applicable: boolean; required_for_task: boolean;
  automatic_value: GradeValue; archive_value?: GradeValue; judge_value: GradeValue | null; value: GradeValue;
  review_state: "not_required" | "historical" | "pending" | "missing_evidence" | "resolved";
  evidence_state: string; reason: string; review_reason: string; source: string;
  method: string; evidence: JudgeEvidence[];
}
export interface JudgeCase {
  id: string; title: string; core_acceptance: string; checks: JudgeCheck[];
}
export interface Finding {
  owner: "agent" | "evaluator" | "unresolved"; category: string; title: string;
  case_id: string; check_id: string; phenomenon: string; required_for_task: boolean;
  evidence: JudgeEvidence[];
}
export interface Judgment {
  id: string; mode: "archive" | "mock"; status: string; revision: number;
  created_at: string; error: { code: string; message: string } | null;
  report: {
    schema_version: number; run_id: string; mode: string; provenance: string;
    skill: { skill_id: string; version_id: string; content_hash: string };
    is_simulation: boolean; model_requests: number;
    cases: JudgeCase[]; findings: Finding[];
  } | null;
  reviews: { case_id: string; check_id: string; value: GradeValue; reason: string; revision: number; created_at: string }[];
}
export const valueLabel = (value: GradeValue | null) =>
  value === 1 ? "通过" : value === 0 ? "未通过" : value === "unknown" ? "未知" : "—";
export const reviewLabels: Record<JudgeCheck["review_state"], string> = {
  not_required: "已判定", historical: "历史复核",
  pending: "待人工复核", missing_evidence: "证据不足", resolved: "人工已复核",
};
export function groupFindings(findings: Finding[]) {
  const groups = new Map<string, { title: string; owner: Finding["owner"]; items: Finding[] }>();
  for (const finding of findings) {
    const key = finding.owner + "/" + finding.category;
    const group = groups.get(key) || { title: finding.title, owner: finding.owner, items: [] };
    group.items.push(finding);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) =>
    Number(b.items.some(i => i.required_for_task)) - Number(a.items.some(i => i.required_for_task)));
}

