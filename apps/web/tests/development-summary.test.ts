import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DevelopmentSummary } from "../components/development-summary";
import type { Recommendation } from "../lib/comparisons";

test("development summary makes action, priority and supporting cases visible", () => {
  const advice: Recommendation = {
    title: "完成前检查交付范围",
    action: "复用现有验收入口检查公开约束。",
    priority_reason: "先保住已经完成的功能成果。",
    phenomenon: "功能完成但范围失败。",
    cause_status: "hypothesis",
    cause: "原因待核查。",
    validation: "先核对既有归档。",
    success_signals: "范围问题可见。",
    guardrails: "保留原评分。",
    refs: [
      { case_id: "U05", observation_id: "scope" },
      { case_id: "O06", observation_id: "scope" },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(DevelopmentSummary, {
      recommendations: [advice],
      onOpen: () => {},
      onCase: () => {},
    }),
  );
  for (const text of [
    advice.title,
    advice.action,
    advice.priority_reason,
    "U05",
    "O06",
    "查看建议详情",
  ])
    assert.ok(html.includes(text), text);
});

test("optional advice leaves no empty card or reason prompt", () => {
  const html = renderToStaticMarkup(
    createElement(DevelopmentSummary, {
      recommendations: [],
      noRecommendationReason: "本次只提供统计，尚未分析开发方向。",
      onOpen: () => {},
      onCase: () => {},
    }),
  );
  assert.equal(html, "");
});
