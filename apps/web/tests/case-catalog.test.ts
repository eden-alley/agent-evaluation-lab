import test from "node:test";
import assert from "node:assert/strict";
import {
  caseFiles,
  caseMessages,
  casePresentation,
  latestDatasetDrafts,
} from "../lib/case-catalog.ts";
import type { QualityCase } from "../lib/quality-types.ts";
import previews from "../lib/case-preview-data.json";

const item = (input: Record<string, unknown> = {}): QualityCase => ({
  case_id: "S05-context-compaction",
  title: "修订后的任务",
  input,
  expected: null,
  categories: ["新类型"],
  requirement_ids: [],
  grading_notes: "",
});

test("approved preview is used only for its exact source version", () => {
  const source = previews.find((p) => p.caseId === "S05-context-compaction")!;
  assert.equal(
    casePresentation(item(), source.sourceHash).keyResult,
    source.keyResult,
  );
  const revised = casePresentation(
    item({ design_metadata: { purpose: "新的规则和金额" } }),
    "different-hash",
  );
  assert.equal(revised.curated, false);
  assert.equal(revised.shortTitle, "修订后的任务");
  assert.equal(revised.summary, "新的规则和金额");
  assert.equal(revised.keyResult, "");
  assert.equal(
    casePresentation({ ...item(), case_id: "unrelated" }, source.sourceHash)
      .curated,
    false,
  );
});

test("latest drafts are selected per dataset without merging repeated case IDs", () => {
  const drafts = [
    { id: "a-new", dataset_id: "a", created_at: "2026-11-08T03:00:00+08:00" },
    { id: "b", dataset_id: "b", created_at: "2026-11-07T00:00:00Z" },
    { id: "a-old", dataset_id: "a", created_at: "2026-11-07T18:00:00Z" },
  ];
  const before = JSON.stringify(drafts);
  assert.deepEqual(
    latestDatasetDrafts(drafts)
      .map((d) => d.id)
      .sort(),
    ["a-new", "b"],
  );
  assert.equal(JSON.stringify(drafts), before);
});

test("arbitrary case inputs retain a readable fallback and tolerate malformed optional metadata", () => {
  const result = casePresentation(
    item({
      design_metadata: ["not an object"],
      messages: [
        null,
        { content: 42 },
        { role: "user", content: "原始任务正文" },
      ],
    }),
    "unknown",
  );
  assert.equal(result.summary, "原始任务正文");
  assert.equal(result.displayGroup, "新类型");
  assert.equal(result.focus, "未标注考察点");
  assert.equal(result.tone, "general");
  assert.deepEqual(caseMessages(item({ messages: null })), []);
  assert.deepEqual(
    caseFiles(
      item({
        workspace_files: [
          null,
          { path: 12 },
          { path: "a.txt", content: "<script>raw</script>\n", bytes: 26 },
        ],
      }),
    ),
    [
      {
        path: "a.txt",
        content: "<script>raw</script>\n",
        bytes: 26,
        sha256: "",
      },
    ],
  );
});
