import assert from "node:assert/strict";
import { test } from "node:test";
import {
  summarizeRun,
  summarizeDimensions,
  compareRuns,
  validateJsonl,
} from "../lib/domain.ts";
import type { EvaluationRun, Trial } from "../lib/types";

const trial = (id: string, patch: Partial<Trial> = {}): Trial => ({
  id,
  case_id: id,
  title: id,
  category: "test",
  case_hash: `hash-${id}`,
  execution_status: "completed",
  verdict: "pass",
  latency_ms: 1000,
  tokens: 100,
  cost: 0.1,
  output: "done",
  error: null,
  trace_id: `trace-${id}`,
  spans: [],
  grades: [],
  ...patch,
});
const run = (
  trials: Trial[],
  patch: Partial<EvaluationRun> = {},
): EvaluationRun => ({
  id: "run",
  name: "fixture",
  origin: "fixture",
  agent_name: "fixture",
  agent_version: "1",
  dataset_id: "ds",
  dataset_version: 1,
  rubric_id: "rub",
  rubric_version: 1,
  total_dataset_cases: 20,
  created_at: "2026-11-05T00:00:00Z",
  status: "completed",
  trials,
  ...patch,
});
test("coverage separates execution, graded verdicts, and pending review", () => {
  const s = summarizeRun(
    run([
      trial("a"),
      trial("b", { verdict: "fail" }),
      trial("c", { verdict: "pending_review" }),
      trial("d", {
        execution_status: "timeout",
        verdict: "ungraded",
        tokens: null,
        cost: null,
      }),
    ]),
  );
  assert.equal(s.selected, 4);
  assert.equal(s.finished, 4);
  assert.equal(s.scored, 2);
  assert.equal(s.passed, 1);
  assert.equal(s.failed, 1);
  assert.equal(s.pending, 1);
  assert.equal(s.execution_errors, 1);
  assert.equal(s.grading_coverage, 0.5);
  assert.equal(s.pass_rate, 0.5);
  assert.equal(s.total_cost, null);
  assert.equal(s.cost_coverage, 3);
  assert.equal(s.total_tokens, null);
});
test("empty runs have unknown ratios and no fabricated zero costs", () => {
  const s = summarizeRun(run([]));
  assert.equal(s.pass_rate, null);
  assert.equal(s.grading_coverage, null);
  assert.equal(s.total_cost, null);
  assert.equal(s.average_latency_ms, null);
});
test("latency averages only observed durations and reports its coverage", () => {
  const s = summarizeRun(
    run([
      trial("a", { latency_ms: 2000 }),
      trial("b", { latency_ms: null }),
      trial("c", { latency_ms: 6000 }),
    ]),
  );
  assert.equal(s.average_latency_ms, 4000);
  assert.equal(s.latency_coverage, 2);
});
test("comparison pairs stable IDs and finds both fixes and regressions", () => {
  const c = compareRuns(
    run([trial("a"), trial("b", { verdict: "fail" })]),
    run([trial("b"), trial("a", { verdict: "fail" })]),
  );
  assert.equal(c.comparable, true);
  assert.equal(c.regressions, 1);
  assert.equal(c.fixes, 1);
  assert.equal(c.rows.find((r) => r.case_id === "a")?.change, "regressed");
});
test("case edits, additions and removals are not regressions", () => {
  const c = compareRuns(
    run([trial("a"), trial("b")]),
    run([trial("a", { case_hash: "changed", verdict: "fail" }), trial("c")], {
      dataset_version: 2,
    }),
  );
  assert.equal(c.regressions, 0);
  assert.deepEqual(c.rows.map((r) => r.change).sort(), [
    "added",
    "modified",
    "removed",
  ]);
});
test("rubric changes and unrelated datasets cannot be scored as regressions", () => {
  for (const patch of [{ rubric_version: 2 }, { dataset_id: "other" }]) {
    const c = compareRuns(
      run([trial("a")]),
      run([trial("a", { verdict: "fail" })], patch),
    );
    assert.equal(c.comparable, false);
    assert.equal(c.regressions, 0);
    assert.equal(c.rows[0].change, "incomparable");
  }
});
test("pending and execution errors are not pass-to-fail changes", () => {
  const c = compareRuns(
    run([trial("a"), trial("b")]),
    run([
      trial("a", { verdict: "pending_review" }),
      trial("b", { verdict: "ungraded", execution_status: "error" }),
    ]),
  );
  assert.equal(c.regressions, 0);
  assert.ok(c.rows.every((r) => r.change === "ungraded"));
});
const row = (id: string) =>
  JSON.stringify({
    schema_version: 1,
    case_id: id,
    input: { prompt: "读文件" },
    expected: null,
    categories: ["文件"],
  });
test("dimension averages exclude missing grades and expose the denominator", () => {
  const grade = (
    score: number | null,
    status: "scored" | "pending_review",
  ) => ({
    dimension_id: "quality",
    name: "质量",
    score,
    status,
    reason: "",
    evidence_span_ids: [],
  });
  const summary = summarizeDimensions(
    run([
      trial("a", { grades: [grade(1, "scored")] }),
      trial("b", { grades: [grade(0, "scored")] }),
      trial("c", { grades: [grade(null, "pending_review")] }),
    ]),
  );
  assert.deepEqual(summary, [
    { id: "quality", name: "质量", mean: 0.5, scored: 2, selected: 3 },
  ]);
});
test("JSONL accepts BOM/CRLF and preserves explicit null expected values", () => {
  const v = validateJsonl(`\uFEFF${row("a")}\r\n${row("b")}\r\n`);
  assert.equal(v.valid, true);
  assert.equal(v.cases.length, 2);
  assert.equal(v.cases[0].expected, null);
  assert.deepEqual(v.categories, ["文件"]);
});
test("bad JSON or duplicate case IDs rejects the whole import with line numbers", () => {
  for (const tail of [row("a"), "{bad"]) {
    const v = validateJsonl(`${row("a")}\n${tail}`);
    assert.equal(v.valid, false);
    assert.equal(v.cases.length, 0);
    assert.equal(v.errors[0].line, 2);
  }
});
test("JSONL rejects empty input, wrong shapes and unknown top-level fields", () => {
  for (const text of [
    "",
    JSON.stringify({
      schema_version: 1,
      case_id: "x",
      input: [],
      expected: null,
    }),
    JSON.stringify({
      schema_version: 2,
      case_id: "x",
      input: {},
      expected: null,
    }),
    JSON.stringify({
      schema_version: 1,
      case_id: "x",
      input: {},
      expected: null,
      unexpected: true,
    }),
  ])
    assert.equal(validateJsonl(text).valid, false);
});
