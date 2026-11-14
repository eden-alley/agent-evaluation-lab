import type { Material } from "./comparisons";
export interface RepeatStats {
  total_calls: number;
  candidate_count: number;
  necessary: number;
  useless: number;
  insufficient: number;
}
export interface RepeatItem {
  event_id: number;
  previous_event_id: number;
  tool: string;
  arguments: Record<string, string>;
  classification: string;
  reason: string;
  changed_files: string[];
  previous_result_visible: boolean;
  file_hashes?: Record<string, string | null>;
  evidence: (Material & { label: string })[];
}
export interface RepeatSide extends RepeatStats {
  version: string;
  status: string;
  items: RepeatItem[];
}
export interface RepetitionMetric {
  improved_cases?: string[];
  regressed_cases?: string[];
  id: string;
  name: string;
  version: string;
  before: number | null;
  after: number | null;
  direction: string;
  paired_cases: number;
  excluded_cases: string[];
  definition: string;
  cross_tool_status: string;
  totals: { baseline: RepeatStats; candidate: RepeatStats };
  cases: {
    case_id: string;
    comparable: boolean;
    reason: string;
    baseline: RepeatSide | null;
    candidate: RepeatSide | null;
  }[];
}
