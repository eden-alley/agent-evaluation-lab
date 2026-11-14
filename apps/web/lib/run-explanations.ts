import type { CaseExplanation } from "./comparisons";

export interface RunExplanation {
  run_id: string;
  case_id: string;
  status: "available" | "not_explained" | "source_changed";
  explanation: CaseExplanation | null;
  source: {
    comparison_id: string;
    report_id: string;
    report_created_at: string;
    report_hash: string;
    side: "baseline" | "candidate";
    method_version: string | null;
    report_is_simulation: boolean;
    analysis_origin: string | null;
  } | null;
}
