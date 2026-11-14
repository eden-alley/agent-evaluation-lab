import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RepetitionMetrics } from "../components/repetition-metrics";
import type { RepeatSide } from "../lib/repetition";

test("repeat table preserves count-based judgement and per-call evidence", () => {
  const side: RepeatSide = {
    version: "exact-repetition-0.1.0",
    status: "complete",
    total_calls: 36,
    candidate_count: 1,
    necessary: 0,
    useless: 1,
    insufficient: 0,
    items: [
      {
        event_id: 18,
        previous_event_id: 13,
        tool: "read_file",
        arguments: { path: "cli.py" },
        classification: "useless",
        reason: "旧结果仍可见且内容相同。",
        changed_files: [],
        previous_result_visible: true,
        evidence: [
          {
            id: "r",
            source: "baseline",
            case_id: "U05",
            kind: "archive",
            path: "events.jsonl",
            sha256: "hash",
            bytes: 10,
            start_line: 18,
            line_count: 1,
            label: "本次调用",
            excerpt: "read_file cli.py",
          },
        ],
      },
    ],
  };
  const metric = {
    id: "useless_exact_repetition",
    name: "无效重复调用（原样重复范围）",
    version: "exact-repetition-0.1.0",
    before: 1,
    after: 1,
    direction: "unchanged",
    paired_cases: 1,
    excluded_cases: [],
    definition: "同工具同参数。",
    cross_tool_status: "not_evaluated",
    totals: { baseline: side, candidate: { ...side, total_calls: 41 } },
    cases: [
      {
        case_id: "U05",
        comparable: true,
        reason: "同口径",
        baseline: side,
        candidate: side,
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(RepetitionMetrics, { metric }),
  );
  for (const text of [
    "本次无明确变化",
    "事件18",
    "前次13",
    "events.jsonl",
    "read_file cli.py",
    "跨工具等价重复",
    "未评估",
  ])
    assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /2\.4%|2\.8%/);
  const unknown = renderToStaticMarkup(
    createElement(RepetitionMetrics, {
      metric: {
        ...metric,
        before: null,
        after: null,
        direction: "insufficient",
        paired_cases: 0,
      },
    }),
  );
  assert.match(unknown, /证据不足/);
  assert.match(unknown, /—/);

  const fullTable = renderToStaticMarkup(
    createElement(RepetitionMetrics, {
      metric: {
        ...metric,
        cases: [
          ...metric.cases,
          {
            case_id: "O08",
            comparable: true,
            reason: "同口径",
            baseline: { ...side, candidate_count: 0, useless: 0, items: [] },
            candidate: side,
          },
          {
            case_id: "U01",
            comparable: false,
            reason: "未判定候选不能记成改善",
            baseline: { ...side, useless: 0, insufficient: 1, items: [] },
            candidate: { ...side, candidate_count: 0, useless: 0, items: [] },
          },
        ],
      },
    }),
  );
  assert.match(fullTable, /逐题总表（3题）/);
  const row = (id: string) =>
    fullTable.match(
      new RegExp(`<tr><th scope="row">${id}</th>(.*?)</tr>`),
    )?.[1];
  assert.match(row("U05") ?? "", /持平/);
  assert.match(row("O08") ?? "", /退步/);
  assert.match(row("U01") ?? "", /无法判断/);
  assert.doesNotMatch(row("U01") ?? "", /持平|改善/);
});
