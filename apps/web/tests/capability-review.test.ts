import test from "node:test";
import assert from "node:assert/strict";
import {
  regressionFirst,
  evidenceOrder,
  metricDirection,
  metricValue,
  type CapabilityMetric,
} from "../lib/capability-review";

test("regressions appear first without changing saved metric or case order", () => {
  const gain = { ...metric, id: "gain", regressed_cases: [] };
  const loss = { ...metric, id: "scope", direction: "regressed" as const };
  const original = [gain, metric, loss];
  assert.deepEqual(
    regressionFirst(original).map((m) => m.id),
    ["scope", "delivery", "gain"],
  );
  assert.equal(original[0].id, "gain");
  const m = {
    ...metric,
    case_evidence: [
      { case_id: "same", before: 1, after: 1, evidence: [] },
      { case_id: "loss", before: 1, after: 0, evidence: [] },
    ],
  };
  assert.equal(evidenceOrder(m)[0].case_id, "loss");
  assert.equal(m.case_evidence[0].case_id, "same");
});

const metric: CapabilityMetric = {
  id: "delivery",
  name: "交付",
  before: 6,
  after: 7,
  paired_cases: 9,
  direction: "improved",
  improved_cases: ["U01", "U05"],
  regressed_cases: ["U02"],
  case_evidence: [],
  excluded: [],
};

test("net improvement cannot hide a regressed case", () => {
  assert.equal(metricDirection(metric), "净进步 · 有回归");
  assert.equal(
    metricDirection({ ...metric, direction: "regressed", before: 7, after: 6 }),
    "净退步 · 有改善",
  );
  assert.equal(
    metricDirection({ ...metric, direction: "mixed", before: 6, after: 6 }),
    "有取舍",
  );
});
test("unknown and empty coverage never render as zero percent", () => {
  assert.equal(metricValue(null, 20), "—");
  assert.equal(metricValue(0, 0), "—");
  assert.equal(metricValue(0, 5), "0 / 5");
  assert.equal(metricValue(16, 20), "16 / 20");
  assert.equal(
    metricDirection({ ...metric, direction: "insufficient" }),
    "无法判断",
  );
});
