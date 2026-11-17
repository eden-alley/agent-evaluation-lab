import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { OutputRecoveryFacts, type RecoveryFacts } from "../components/output-recovery";

test("complete response is shown separately from task acceptance and budget stop", () => {
  const evidence = { path: "case/events.jsonl", line: 4, event_id: 7 };
  const data: RecoveryFacts = {
    truncations: [{ evidence, completion_tokens: 4096, tools_executed: false }],
    recovery: [{ status: "scheduled", evidence }, { status: "response_complete", evidence }],
    stop: { reason: "token_limit", text: "预算已耗尽", evidence },
    task_success: null,
    limitations: "完整响应不代表任务通过",
  };
  const html = renderToStaticMarkup(createElement(OutputRecoveryFacts, { runId: "r", data }));
  assert.match(html, /准备继续/);
  assert.match(html, /收到完整响应/);
  assert.match(html, /完整响应不代表任务通过/);
  assert.match(html, /token 总额上限/);
  assert.match(html, /本次工具调用均未执行/);
  assert.match(html, /download=true/);
  assert.doesNotMatch(html, /恢复成功|任务已通过/);
});

test("missing records do not become a confident no-truncation or success claim", () => {
  const data: RecoveryFacts = { truncations: [], recovery: [], stop: null,
    task_success: null, limitations: "未记录不等于未发生" };
  const html = renderToStaticMarkup(createElement(OutputRecoveryFacts, { runId: "r", data }));
  assert.match(html, /现有记录未确认输出截断/);
  assert.match(html, /归档未记录恢复过程/);
  assert.match(html, /未记录不等于未发生/);
});
