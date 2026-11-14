import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewMethod } from "../components/review-method";

test("report renders its frozen method and limits of output checks", () => {
  const html = renderToStaticMarkup(
    createElement(ReviewMethod, {
      delivery: {
        id: "delivery-one",
        comparison_id: "comparison-one",
        provided_at: "2026-11-13T10:00:00Z",
        channel: "capability-review-cli",
        read_status: "not_verified",
        skill: {
          skill_id: "skill-one",
          version_id: "version-frozen",
          content_hash: "saved-hash",
          name: "本次分析方法",
          method_version: "0.4.0",
          content: "固定方法正文，包含任务讲解和工程复盘。",
        },
        requirements: { explanation_case_ids: ["U05"] },
        scope: "仅证明正文已提供。",
      },
      checks: {
        status: "passed",
        semantic_status: "not_evaluated",
        model_compliance: "not_verified",
        checks: [
          { id: "method", title: "方法版本与提供记录一致", status: "passed" },
        ],
        scope: "语义与原因仍需核查。",
      },
    }),
  );
  for (const text of [
    "version-frozen",
    "saved-hash",
    "delivery-one",
    "U05",
    "固定方法正文",
    "尚未验证",
    "结构与引用",
  ])
    assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /Agent已阅读|模型已遵循|语义通过/);
});

test("historical report never receives the currently published method by default", () => {
  const html = renderToStaticMarkup(createElement(ReviewMethod, {}));
  assert.match(html, /未记录/);
  assert.doesNotMatch(html, /已提供正文|检查通过/);
});
