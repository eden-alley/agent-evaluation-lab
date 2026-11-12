import test from "node:test";
import assert from "node:assert/strict";
import { groupFindings } from "../lib/judging";
import type { Finding } from "../lib/judging";

test("one case can have multiple checks without becoming multiple affected cases", () => {
  const base: Finding = { owner: "agent", category: "delivery", title: "交付缺失",
    case_id: "U05", check_id: "delivery", phenomenon: "未交付", required_for_task: true, evidence: [] };
  const groups = groupFindings([base, { ...base, check_id: "self_test" },
    { ...base, owner: "evaluator", title: "评分器误报" }]);
  assert.equal(groups.length, 2);
  assert.equal(new Set(groups[0].items.map(i => i.case_id)).size, 1);
  assert.equal(groups[1].owner, "evaluator");
});

test("required findings precede diagnostic findings and preserve evidence references", () => {
  const evidence = [{ path: "evidence.json", label: "输出", sha256: "abc", excerpt: "事实", truncated: false }];
  const base: Finding = { owner: "agent", category: "efficiency", title: "重复验证",
    case_id: "U03", check_id: "efficiency", phenomenon: "重复", required_for_task: false, evidence };
  const groups = groupFindings([base, { ...base, category: "result", title: "结果失败", required_for_task: true }]);
  assert.equal(groups[0].title, "结果失败");
  assert.deepEqual(groups[0].items[0].evidence, evidence);
});

