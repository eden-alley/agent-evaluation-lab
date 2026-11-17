import test from "node:test";
import assert from "node:assert/strict";
import {
  visibleMetricReport,
  analysisStateText,
  developmentAdvice,
} from "../lib/comparisons";
import type { Comparison, ComparisonReport } from "../lib/comparisons";
import type { MetricReport } from "../lib/capability-review";

test("statistics are visible before external analysis is submitted", () => {
  const table = { registry_version: "frozen" } as MetricReport;
  const comparison = {
    metric_report: table,
    analysis_state: "analysis_pending",
  } as Comparison;
  assert.equal(visibleMetricReport(comparison, null, ""), table);
  assert.equal(analysisStateText(comparison.analysis_state), "等待分析提交");
});

test("selected reports keep their own statistics and never borrow the current table", () => {
  const comparison = {
    metric_report: { registry_version: "created" },
  } as Comparison;
  const report = {
    metric_report: { registry_version: "historical" },
    recommendations: [],
  } as unknown as ComparisonReport;
  assert.equal(
    visibleMetricReport(comparison, report, "old")?.registry_version,
    "historical",
  );
  assert.equal(
    visibleMetricReport(
      comparison,
      { recommendations: [] } as unknown as ComparisonReport,
      "legacy",
    ),
    undefined,
  );
  assert.equal(visibleMetricReport(comparison, null, "loading-old"), undefined);
  assert.deepEqual(developmentAdvice(report), []);
});

test("providing a Skill remains pending until a report receipt exists", () => {
  assert.equal(analysisStateText("analysis_pending"), "等待分析提交");
  assert.equal(analysisStateText("report_received"), "报告已收到");
});
