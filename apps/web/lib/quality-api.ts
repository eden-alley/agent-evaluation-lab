import { request } from "./api";
import type {
  DatasetDraft,
  DatasetVersion,
  DraftSummary,
  Integration,
  QualityReport,
  Skill,
  SkillVersion,
  VersionSummary,
} from "./quality-types";
const id = encodeURIComponent;
const post = (payload?: unknown): RequestInit => ({
  method: "POST",
  ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
});
export const qualityApi = {
  integration: () => request<Integration>("/integration"),
  contract: () => request<Record<string, unknown>>("/integration/contract"),
  drafts: (project: string) =>
    request<{ items: DraftSummary[] }>(
      `/projects/${id(project)}/dataset-drafts`,
    ),
  draft: (draft: string) =>
    request<DatasetDraft>(`/dataset-drafts/${id(draft)}`),
  report: (draft: string, report: string) =>
    request<QualityReport>(
      `/dataset-drafts/${id(draft)}/reports/${id(report)}`,
    ),
  decide: (
    draft: string,
    decision: "approve" | "reject",
    report_id: string | null,
    note: string,
  ) =>
    request<{ draft: DatasetDraft; version: DatasetVersion | null }>(
      `/dataset-drafts/${id(draft)}/decision`,
      post({ decision, report_id, note }),
    ),
  versions: (project: string) =>
    request<{ items: VersionSummary[] }>(
      `/projects/${id(project)}/dataset-versions`,
    ),
  version: (version: string) =>
    request<DatasetVersion>(`/dataset-versions/${id(version)}`),
  skills: () => request<{ items: Skill[] }>("/skills"),
  skill: (skill: string) => request<Skill>(`/skills/${id(skill)}`),
  createSkill: (value: {
    name: string;
    description: string;
    kind: "evaluation" | "business";
    tags: string[];
  }) => request<Skill>("/skills", post(value)),
  saveSkill: (skill: string, content: string, change_note: string) =>
    request<SkillVersion>(
      `/skills/${id(skill)}/versions`,
      post({ content, change_note }),
    ),
  publishSkill: (skill: string, version: string) =>
    request<Skill>(
      `/skills/${id(skill)}/versions/${id(version)}/publish`,
      post(),
    ),
};
