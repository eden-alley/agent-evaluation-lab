import test from "node:test";
import assert from "node:assert/strict";
import { changedChecks, statusLabel } from "../lib/rechecking";

test("rechecking changes describe checking corrections without inventing capability gains", () => {
  const checks = [
    { id: "result", value: 0 as const, historical_value: 0 as const },
    { id: "repeatable", value: "unknown" as const, historical_value: 0 as const },
    { id: "self_test", value: 0 as const, historical_value: 0 as const },
  ];
  assert.deepEqual(changedChecks(checks).map(c => c.id), ["repeatable"]);
  assert.equal(statusLabel("failed"), "检查未完成");
  assert.equal(statusLabel("completed"), "检查已完成");
});
