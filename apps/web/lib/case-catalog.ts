import previews from "./case-preview-data.json";
import type { DatasetDraft, DraftSummary, QualityCase } from "./quality-types";

export type CaseTone =
  "data" | "context" | "clarify" | "verify" | "evidence" | "resume" | "general";
export interface CasePresentation {
  shortTitle: string;
  summary: string;
  focus: string;
  displayGroup: string;
  tone: CaseTone;
  preview: string[][];
  keyResult: string;
  contrast: string;
  difficulty?: string;
  scenario?: string;
  task?: string;
  acceptance?: string;
  readiness?: string;
  notice?: string;
  curated: boolean;
}
export interface CatalogEntry {
  key: string;
  draft: DatasetDraft;
  item: QualityCase;
  presentation: CasePresentation;
}

export function objectValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
export function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
export function caseMessages(item: QualityCase) {
  const messages = item.input.messages;
  if (!Array.isArray(messages)) return [];
  return messages.flatMap((value, i) => {
    const message = objectValue(value);
    return typeof message.content === "string"
      ? [
          {
            index: typeof message.index === "number" ? message.index : i + 1,
            role: textValue(message.role),
            content: message.content,
          },
        ]
      : [];
  });
}
export function caseFiles(item: QualityCase) {
  const files = item.input.workspace_files;
  if (!Array.isArray(files)) return [];
  return files.flatMap((value) => {
    const file = objectValue(value);
    return typeof file.path === "string" && typeof file.content === "string"
      ? [
          {
            path: file.path,
            content: file.content,
            bytes: typeof file.bytes === "number" ? file.bytes : null,
            sha256: textValue(file.sha256),
          },
        ]
      : [];
  });
}

const focusTones: Record<string, CaseTone> = {
  文件与数据: "data",
  上下文管理: "context",
  交互澄清: "clarify",
  任务验证: "verify",
  错误处理: "verify",
  资料与引用: "evidence",
  中断恢复: "resume",
};
const groupOrder = [
  "常见用户任务",
  "代码能力专项",
  "其他能力",
  "用户需求任务 · 文件与数据",
  "能力专项 · 上下文管理",
  "能力专项 · 交互澄清",
  "能力专项 · 修复与验证",
  "能力专项 · 资料与引用",
  "能力专项 · 中断恢复",
];

export function casePresentation(
  item: QualityCase,
  contentHash: string,
): CasePresentation {
  // Editorial summaries from the approved preview are tied to the immutable
  // imported payload. A revised or unrelated case must not inherit stale claims.
  const preview = previews.find(
    (p) => p.caseId === item.case_id && p.sourceHash === contentHash,
  );
  if (preview)
    return {
      ...preview,
      tone: focusTones[preview.focus] || "general",
      curated: true,
    };
  const metadata = objectValue(item.input.design_metadata);
  const focus =
    textValue(metadata.focus) || textValue(item.input.focus) || "未标注考察点";
  const group = textValue(item.input.group) || item.categories[0] || "其他题目";
  const introduction = textValue(metadata.summary);
  const summary =
    introduction ||
    textValue(metadata.purpose) ||
    textValue(item.input.prompt) ||
    caseMessages(item)[0]?.content ||
    "查看完整题目与判定依据。";
  return {
    shortTitle: item.title,
    summary:
      introduction ||
      (summary.length > 90 ? summary.slice(0, 90) + "…" : summary),
    focus,
    displayGroup: group,
    tone: focusTones[focus] || "general",
    preview: introduction
      ? []
      : caseMessages(item)
          .slice(0, 3)
          .map((m) => [
            `第 ${m.index} 轮`,
            m.content.length > 220 ? m.content.slice(0, 220) + "…" : m.content,
          ]),
    keyResult: "",
    contrast: "",
    difficulty: textValue(metadata.difficulty),
    scenario: textValue(metadata.scenario),
    task: textValue(metadata.task),
    acceptance: textValue(metadata.acceptance),
    readiness: textValue(metadata.readiness),
    curated: false,
    notice: item.categories.includes("机制适配待实现")
      ? "机制适配待实现；请查看执行条件与控制协议。"
      : undefined,
  };
}

export function latestDatasetDrafts<
  T extends Pick<DraftSummary, "id" | "dataset_id" | "created_at">,
>(drafts: T[]): T[] {
  const latest = new Map<string, T>();
  for (const draft of drafts) {
    const old = latest.get(draft.dataset_id);
    if (
      !old ||
      new Date(draft.created_at).getTime() >
        new Date(old.created_at).getTime() ||
      (draft.created_at === old.created_at && draft.id > old.id)
    ) {
      latest.set(draft.dataset_id, draft);
    }
  }
  return [...latest.values()];
}

export function catalogEntries(drafts: DatasetDraft[]): CatalogEntry[] {
  return latestDatasetDrafts(drafts)
    .flatMap((draft) =>
      draft.payload.cases.map((item) => ({
        key: `${draft.id}/${item.case_id}`,
        draft,
        item,
        presentation: casePresentation(item, draft.content_hash),
      })),
    )
    .sort((a, b) => {
      const groupA = a.presentation.displayGroup,
        groupB = b.presentation.displayGroup;
      const rank = (group: string) =>
        groupOrder.includes(group)
          ? groupOrder.indexOf(group)
          : groupOrder.length;
      return (
        rank(groupA) - rank(groupB) ||
        groupA.localeCompare(groupB, "zh-CN") ||
        a.item.case_id.localeCompare(b.item.case_id) ||
        a.draft.id.localeCompare(b.draft.id)
      );
    });
}
