import test from "node:test";
import assert from "node:assert/strict";
import { reviewCoverageText } from "../lib/review-coverage";

test("selective explanation does not make full statistics look incomplete", () => {
  const text = reviewCoverageText(
    {
      mode: "key_cases",
      provided: 4,
      planned: 4,
      total_cases: 20,
      case_ids: ["U02", "U03", "U05", "O06"],
    },
    20,
  );
  assert.match(text, /20题已统计/);
  assert.match(text, /4道关键题/);
  assert.doesNotMatch(text, /4\/20|未完成|剩余16/);
});

test("legacy report coverage retains its original meaning", () => {
  assert.match(
    reviewCoverageText({ provided: 1, planned: 20, case_ids: ["U05"] }, 20),
    /1\/20/,
  );
  assert.match(
    reviewCoverageText(
      {
        mode: "key_cases",
        provided: 0,
        planned: 0,
        total_cases: 20,
        case_ids: [],
      },
      20,
    ),
    /0道关键题/,
  );
});
