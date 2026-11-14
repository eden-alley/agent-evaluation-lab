import type { ComparisonReport } from "./comparisons";

export function reviewCoverageText(
  coverage: ComparisonReport["explanation_coverage"],
  total: number,
) {
  if (coverage?.mode === "key_cases")
    return `${coverage.total_cases ?? total}题已统计 · ${coverage.provided}道关键题已讲解`;
  return `已提供 ${coverage?.provided ?? 0}/${coverage?.planned ?? total} 题的过程讲解`;
}
