import test from "node:test";
import assert from "node:assert/strict";
import {
  metricDifference,
  affectedCases,
  demonstration,
  evidencePreview,
  reviewScopeFor,
  developmentAdvice,
} from "../lib/comparisons";
import type { ComparisonReport } from "../lib/comparisons";

test("small selections cannot choose batch advice and size alone never selects formal", () => {
  for (const count of [1, 2, 3])
    assert.equal(reviewScopeFor(count, "formal_batch"), "focused");
  assert.equal(reviewScopeFor(20), "focused");
  assert.equal(reviewScopeFor(20, "formal_batch"), "formal_batch");
});

test("development advice is batch-only while saved legacy reports keep their content", () => {
  const r = {
    recommendations: [{ title: "batch recommendation" }],
    review_policy: { recommendations_allowed: false },
  } as ComparisonReport;
  assert.deepEqual(developmentAdvice(r), []);
  r.review_policy!.recommendations_allowed = true;
  assert.equal(developmentAdvice(r)[0].title, "batch recommendation");
  delete r.review_policy;
  assert.equal(developmentAdvice(r).length, 1);
  assert.deepEqual(developmentAdvice(null), []);
});

test("unknown or invalid resource values never become measured zeros", () => {
  assert.equal(metricDifference(null, 0), null);
  assert.equal(metricDifference(1, Number.NaN), null);
  assert.equal(metricDifference("30", 22), null);
  assert.equal(metricDifference(30, 22), -8);
});

test("event previews preserve failure evidence without the file hash inventory", () => {
  const raw =
    JSON.stringify({
      event_id: 97,
      type: "tool_result",
      tool: "run_shell",
      exit_code: 1,
      data: "AssertionError: 0",
      files: { "unrelated.py": "long-sha256" },
    }) +
    "\n" +
    JSON.stringify({
      event_id: 98,
      type: "final_response",
      stop_reason: "max_steps",
      text: "已停止",
    });
  const preview = evidencePreview("run/U05/events.jsonl", raw);
  assert.match(preview, /97.*tool_result/);
  assert.match(preview, /exit_code=1/);
  assert.match(preview, /AssertionError: 0/);
  assert.match(preview, /max_steps/);
  assert.doesNotMatch(preview, /long-sha256|unrelated.py/);
  assert.equal(evidencePreview("events.jsonl", "invalid {"), "invalid {");
  assert.equal(evidencePreview("notes.txt", raw), raw);
});

test("multiple observations from one case remain one supporting case", () => {
  assert.equal(
    affectedCases([
      { case_id: "U05", observation_id: "a" },
      { case_id: "U05", observation_id: "b" },
    ]),
    1,
  );
  assert.equal(
    affectedCases([
      { case_id: "U05", observation_id: "a" },
      { case_id: "U03", observation_id: "a" },
    ]),
    2,
  );
});

test("scripted analysis is a demonstration even when both run sources exist", () => {
  assert.equal(
    demonstration({
      is_simulation: false,
      analyst: { kind: "offline_fixture" },
    }),
    true,
  );
  assert.equal(
    demonstration({ is_simulation: true, analyst: { kind: "external_agent" } }),
    true,
  );
  assert.equal(
    demonstration({
      is_simulation: false,
      analyst: { kind: "external_agent" },
    }),
    false,
  );
});
