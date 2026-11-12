"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Database, ArrowUpRight } from "lucide-react";
import { api } from "../lib/api";
import { qualityApi } from "../lib/quality-api";
import type { Project } from "../lib/types";
import type {
  DatasetDraft,
  DatasetVersion,
  DraftSummary,
  VersionSummary,
} from "../lib/quality-types";
import { Header, Tabs } from "./report-ui";
import { QualityDetail } from "./quality-detail";
import { CaseCatalog } from "./case-catalog";
import { catalogEntries, latestDatasetDrafts } from "../lib/case-catalog";

export function DatasetWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]),
    [projectId, setProjectId] = useState("");
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  async function load() {
    setLoading(true);
    setError("");
    try {
      const rows = (await api.projects()).items;
      setProjects(rows);
      const requestedProject = new URLSearchParams(window.location.search).get(
        "project",
      );
      setProjectId((old) =>
        rows.some((p) => p.id === old)
          ? old
          : rows.find((p) => p.id === requestedProject)?.id ||
            rows[0]?.id ||
            "",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取项目失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <>
      <div className="project-context">
        <label htmlFor="dataset-project">当前项目</label>
        <select
          className="input compact-select"
          id="dataset-project"
          disabled={busy || loading}
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {!projects.length && <option value="">尚无项目</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <a className="click small" href="/projects">
          管理项目 <ArrowUpRight className="inline-icon" size={12} />
        </a>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
          <button className="button small" onClick={load}>
            重试
          </button>
        </div>
      )}
      {loading ? (
        <p className="pad muted">正在读取项目…</p>
      ) : projectId ? (
        <ProjectDatasets
          key={projectId}
          projectId={projectId}
          onBusy={setBusy}
        />
      ) : (
        <>
          <Header
            title="数据集"
            desc="接收外部 Coding Agent 交付的用例与质量报告。"
          />
          <div className="panel empty">
            <Database size={30} className="empty-icon" />
            <h2>先创建一个项目</h2>
            <p>
              在项目中说明任务目标，再连接外部 Coding
              Agent，使用已发布的技能生成评测集草案。
            </p>
            <a className="button primary" href="/projects">
              创建项目
            </a>
            <a className="button" href="/settings">
              查看接入方式
            </a>
          </div>
        </>
      )}
    </>
  );
}

function ProjectDatasets({
  projectId,
  onBusy,
}: {
  projectId: string;
  onBusy: (busy: boolean) => void;
}) {
  const [drafts, setDrafts] = useState<DraftSummary[]>([]),
    [versions, setVersions] = useState<VersionSummary[]>([]),
    [tab, setTab] = useState("待审草案");
  const [view, setView] = useState("评测题库"),
    [catalogDrafts, setCatalogDrafts] = useState<DatasetDraft[]>([]),
    [selectedDraftId, setSelectedDraftId] = useState(""),
    [catalogError, setCatalogError] = useState("");
  const [draft, setDraft] = useState<DatasetDraft | null>(null),
    [version, setVersion] = useState<DatasetVersion | undefined>();
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [detailLoading, setDetailLoading] = useState(false);
  const epoch = useRef(0),
    loadEpoch = useRef(0);
  const activeDraft =
    catalogDrafts.find((d) => d.id === selectedDraftId) || catalogDrafts[0];
  const entries = useMemo(
    () => catalogEntries(activeDraft ? [activeDraft] : []),
    [activeDraft],
  );
  function selectDataset(id: string) {
    setSelectedDraftId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("project", projectId);
    url.searchParams.set("draft", id);
    window.history.replaceState(null, "", url);
  }
  async function load() {
    const request = ++loadEpoch.current;
    setLoading(true);
    setError("");
    setCatalogError("");
    try {
      const [a, b] = await Promise.all([
        qualityApi.drafts(projectId),
        qualityApi.versions(projectId),
      ]);
      if (request !== loadEpoch.current) return;
      setDrafts(a.items);
      setVersions(b.items);
      // The library shows the newest immutable draft of each dataset. Older
      // submissions and fixed versions remain available in the review view.
      const details = await Promise.allSettled(
        latestDatasetDrafts(a.items).map((d) => qualityApi.draft(d.id)),
      );
      if (request !== loadEpoch.current) return;
      if (details.some((result) => result.status === "rejected")) {
        setCatalogDrafts([]);
        setCatalogError("部分题目读取失败，请重试。草案与版本仍可单独查看。");
      } else {
        const loaded = details
          .flatMap((result) =>
            result.status === "fulfilled" ? [result.value] : [],
          )
          .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
        const requestedDraft = new URLSearchParams(window.location.search).get(
          "draft",
        );
        setCatalogDrafts(loaded);
        setSelectedDraftId(
          (old) =>
            loaded.find((d) => d.id === old)?.id ||
            loaded.find((d) => d.id === requestedDraft)?.id ||
            loaded[0]?.id ||
            "",
        );
      }
    } catch (e) {
      if (request === loadEpoch.current)
        setError(e instanceof Error ? e.message : "读取失败");
    } finally {
      if (request === loadEpoch.current) setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    return () => {
      loadEpoch.current++;
      epoch.current++;
    };
  }, []);
  async function open(id: string, isVersion = false) {
    const request = ++epoch.current;
    setDraft(null);
    setVersion(undefined);
    setDetailLoading(true);
    setError("");
    try {
      if (isVersion) {
        const v = await qualityApi.version(id);
        if (request !== epoch.current) return;
        setVersion(v);
        setDraft({
          id: v.draft_id,
          project_id: v.project_id,
          dataset_id: v.dataset_id,
          base_version_id: v.payload.base_version_id,
          content_hash: v.content_hash,
          created_at: v.created_at,
          status: "approved",
          payload: v.payload,
          checks: v.checks,
          latest_report: v.quality_report,
          report_history: [v.quality_report],
          decision: v.decision,
          metrics: {
            total_cases: v.payload.cases.length,
            requirements: v.payload.requirements.length,
            structurally_checked_cases: v.payload.cases.length,
            reviewed_cases: v.quality_report.payload.reviewed_case_ids.length,
            covered_requirements: v.quality_report.payload.coverage.filter(
              (c) => c.status === "covered",
            ).length,
            blockers: [
              ...v.checks,
              ...v.quality_report.payload.findings,
            ].filter((f) => f.severity === "blocker").length,
            warnings: [
              ...v.checks,
              ...v.quality_report.payload.findings,
            ].filter((f) => f.severity === "warning").length,
          },
        });
      } else {
        const d = await qualityApi.draft(id);
        if (request === epoch.current) setDraft(d);
      }
    } catch (e) {
      if (request === epoch.current)
        setError(e instanceof Error ? e.message : "读取详情失败");
    } finally {
      if (request === epoch.current) setDetailLoading(false);
    }
  }
  return (
    <>
      {draft && (
        <QualityDetail
          key={draft.id + (version?.id || "")}
          draft={draft}
          version={version}
          onBusy={onBusy}
          onBack={() => {
            setDraft(null);
            setVersion(undefined);
            void load();
          }}
          onChange={(next) => {
            setDraft(next);
            void load();
          }}
        />
      )}
      <div hidden={!!draft}>
        <Header
          title="数据集"
          desc="选择一套评测，查看任务和验收标准。"
          action={
            <button
              className="button small"
              disabled={loading || detailLoading}
              onClick={load}
            >
              刷新
            </button>
          }
        />
        <div className="run-tabs">
          <Tabs
            labels={["评测题库", "草案与版本"]}
            active={view}
            set={setView}
          />
        </div>
        {error && (
          <div role="alert" className="error section-bottom">
            {error}
            <button className="button small" onClick={load}>
              重试
            </button>
          </div>
        )}
        <div hidden={view !== "评测题库"}>
          {loading && (
            <p role="status" className="pad muted">
              正在读取题目…
            </p>
          )}
          {!loading && catalogError && (
            <div className="error" role="alert">
              {catalogError}
              <button className="button small" onClick={load}>
                重试
              </button>
            </div>
          )}
          <div hidden={loading || !!catalogError}>
            {activeDraft && (
              <div className="project-context">
                <label htmlFor="active-dataset">评测集</label>
                <select
                  id="active-dataset"
                  className="input"
                  value={activeDraft.id}
                  onChange={(e) => selectDataset(e.target.value)}
                >
                  {catalogDrafts.map((d) => (
                    <option value={d.id} key={d.id}>
                      {d.payload.name} · {d.payload.cases.length} 题
                    </option>
                  ))}
                </select>
                <span className="small muted">
                  {activeDraft.status === "approved"
                    ? "已确认"
                    : activeDraft.status === "rejected"
                      ? "已退回"
                      : "待审阅"}
                </span>
              </div>
            )}
            <CaseCatalog
              key={activeDraft?.id}
              entries={entries}
              overview={
                entries.some((entry) => entry.presentation.readiness)
                  ? activeDraft?.payload.task_description
                  : undefined
              }
              onReport={open}
            />
          </div>
          {detailLoading && (
            <p role="status" className="pad muted">
              正在读取质量报告…
            </p>
          )}
        </div>
        <div hidden={view !== "草案与版本"}>
          <div className="panel">
            <div className="panel-head">
              <div>
                <h2>交付与版本</h2>
                <p>真实工作区数据 · 来源与内容哈希随版本保存</p>
              </div>
              <button
                className="button small"
                disabled={loading || detailLoading}
                onClick={load}
              >
                刷新
              </button>
            </div>
            <Tabs
              labels={["待审草案", "全部草案", "固定版本"]}
              active={tab}
              set={setTab}
            />
            {loading || detailLoading ? (
              <p role="status" className="pad muted">
                {detailLoading ? "正在读取详情…" : "正在加载…"}
              </p>
            ) : tab === "固定版本" ? (
              versions.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>数据集</th>
                        <th>版本</th>
                        <th>用例数</th>
                        <th>确认时间</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {versions.map((v) => (
                        <tr key={v.id}>
                          <td>{v.name}</td>
                          <td>v{v.version}</td>
                          <td>{v.case_count}</td>
                          <td className="small muted">
                            {new Date(v.created_at).toLocaleString("zh-CN")}
                          </td>
                          <td>
                            <button
                              className="button small"
                              onClick={() => open(v.id, true)}
                            >
                              查看固定版本
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty">
                  <h2>尚无确认版本</h2>
                  <p>审阅草案和质量报告后，可将其确认为固定版本。</p>
                </div>
              )
            ) : (
              <DraftTable
                items={drafts.filter(
                  (d) => tab === "全部草案" || d.status === "pending",
                )}
                open={open}
              />
            )}
          </div>
          <p className="small muted section-note">
            评测执行器尚未接入。此处确认的是评测集版本，不是被测智能体的评测成绩。
          </p>
        </div>
      </div>
    </>
  );
}
function DraftTable({
  items,
  open,
}: {
  items: DraftSummary[];
  open: (id: string) => void;
}) {
  if (!items.length)
    return (
      <div className="empty">
        <Database size={28} className="empty-icon" />
        <h2>等待外部 Agent 交付草案</h2>
        <p>
          连接平台后，让编程助手读取项目需求、选用已发布技能，并提交评测集与检查报告。
        </p>
        <a className="button" href="/skills">
          查看内置技能
        </a>
      </div>
    );
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>草案</th>
            <th>用例数</th>
            <th>外部已检查</th>
            <th>阻断 / 待确认</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td>
                <strong>{d.name}</strong>
                <p className="small muted">{d.source.client}</p>
              </td>
              <td>{d.metrics.total_cases}</td>
              <td>
                {d.metrics.reviewed_cases}/{d.metrics.total_cases}
              </td>
              <td>
                {d.metrics.blockers} / {d.metrics.warnings}
              </td>
              <td>
                <span
                  className={
                    "badge " +
                    (d.status === "approved"
                      ? "good"
                      : d.status === "rejected"
                        ? "bad"
                        : "warn")
                  }
                >
                  {d.status === "pending"
                    ? "待审阅"
                    : d.status === "approved"
                      ? "已确认"
                      : "已退回"}
                </span>
              </td>
              <td>
                <button className="button small" onClick={() => open(d.id)}>
                  查看质量报告
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
