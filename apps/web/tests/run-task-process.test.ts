import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TaskProcessBody } from "../components/run-task-process";
import type { RunExplanation } from "../lib/run-explanations";
import type { ImportedCase } from "../lib/imported-runs";

const item = {
  id: "U05",
  core_acceptance: "fail",
  task: { turns: [{ content: "增加只读查询命令。" }] },
  metrics: { stop_reasons: ["max_steps"] },
  checks: [
    {
      id: "scope",
      required_for_task: true,
      value: 0,
      reason: "原测试被改动。",
    },
  ],
} as ImportedCase;

test("task explanation presents background, key feedback and result before raw files", () => {
  const ref = {
    id: "e",
    case_id: "U05",
    source: "candidate",
    kind: "archive",
    path: "events.jsonl",
    sha256: "fixed",
    bytes: 10,
    excerpt: "raw original",
    display_excerpt: "实际反馈：测试通过",
  } as const;
  const data = {
    run_id: "run",
    case_id: "U05",
    status: "available",
    explanation: {
      case_id: "U05",
      focus: "candidate",
      background: "需要只读查看实际限制。",
      stages: [
        {
          title: "完成功能后越界",
          text: "功能通过，但原测试被改动。",
          evidence: [ref],
        },
      ],
      result: { text: "功能通过，范围不通过。", evidence: [ref] },
      limitations: [],
    },
    source: {
      comparison_id: "comparison",
      report_id: "report",
      report_created_at: "2026-11-14T10:00:00Z",
      report_hash: "fixed-hash",
      side: "candidate",
      method_version: "0.7.0",
      report_is_simulation: false,
      analysis_origin: "offline_program",
    },
  } as RunExplanation;
  const html = renderToStaticMarkup(
    createElement(TaskProcessBody, {
      item,
      data,
      children: createElement("div", {}, "RAW_FILES_SENTINEL"),
    }),
  );
  for (const text of [
    "需要只读查看实际限制",
    "完成功能后越界",
    "功能通过，范围不通过",
    "实际反馈：测试通过",
  ])
    assert.ok(html.includes(text), text);
  assert.ok(!html.includes("RAW_FILES_SENTINEL"));
  assert.match(html, /查看原始事件与交付文件/);
  assert.match(html, /0.7.0/);
});

test("ordinary case has an automatic summary without invented process narration", () => {
  const html = renderToStaticMarkup(
    createElement(TaskProcessBody, {
      item,
      data: {
        status: "not_explained",
        explanation: null,
        source: null,
      } as RunExplanation,
    }),
  );
  assert.match(html, /增加只读查询命令/);
  assert.match(html, /原测试被改动/);
  assert.match(html, /达到操作次数上限/);
  assert.match(html, /自动摘要/);
  assert.doesNotMatch(html, /关键经过|已完成过程分析/);
});

test("changed evidence is visible and does not silently reuse the old narration", () => {
  const html = renderToStaticMarkup(
    createElement(TaskProcessBody, {
      item,
      data: {
        status: "source_changed",
        explanation: null,
        source: null,
      } as RunExplanation,
    }),
  );
  assert.match(html, /原件已变化/);
  assert.match(html, /查看原始事件与交付文件/);
});
