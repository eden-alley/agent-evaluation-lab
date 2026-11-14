import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TaskNarrative } from "../components/task-narrative";
import type { CaseExplanation } from "../lib/comparisons";

test("narrative preserves concrete inputs, reply intervals and the final acceptance distinction", () => {
  const explanation: CaseExplanation = {
    case_id: "U02",
    focus: "candidate",
    background:
      "输入 `ab ab ab`，原结果后两段带空格。\n\n```text\n期望：[ab, ab, ab]\n```",
    stages: [
      {
        title: "第 23—31 次：原问题已消失",
        text: "第31次得到正确结果。\n\n关闭清理仍保留空格。",
        evidence: [],
      },
      {
        title: "第 33—60 次：继续追加检查",
        text: "没有再改核心源码，直到上限停止。",
        evidence: [],
      },
    ],
    result: {
      text: "代码改好了，交付没有完成。\n\n后来5项独立回归通过；规定自测、报告仍缺失，留下17个范围外文件。",
      evidence: [],
    },
    limitations: [],
  };
  const html = renderToStaticMarkup(
    createElement(TaskNarrative, { explanation, renderEvidence: () => null }),
  );
  assert.ok(html.indexOf("代码改好了") < html.indexOf("输入"));
  assert.ok(html.indexOf("第 33—60 次") < html.indexOf("后来5项"));
  assert.match(html, /<code>ab ab ab<\/code>/);
  assert.match(html, /<pre[^>]*><code>/);
  assert.ok(html.includes("17个范围外文件"));
  assert.equal((html.match(/代码改好了/g) || []).length, 1);
});

test("narrative text stays escaped rather than executing embedded markup", () => {
  const e = {
    case_id: "x",
    focus: "candidate",
    background: "<script>alert(1)</script>",
    stages: [],
    result: { text: "旧结果", evidence: [] },
    limitations: [],
  } as CaseExplanation;
  const html = renderToStaticMarkup(
    createElement(TaskNarrative, {
      explanation: e,
      renderEvidence: () => null,
    }),
  );
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});
