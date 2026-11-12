"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import { artifactUrl, dimensions, dimensionLabel } from "../lib/imported-runs";
import type {
  ImportedRun,
  ImportedCase,
  EvidenceFile,
} from "../lib/imported-runs";
import { Header, Badge, Tabs } from "./report-ui";
import { runCasePresentation } from "../lib/run-case-introductions";
import { TraceNarrative } from "./trace-narrative";

export function ImportedRuns({ id }: { id?: string }) {
  const [runs, setRuns] = useState<ImportedRun[]>([]),
    [run, setRun] = useState<ImportedRun | null>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        if (id) {
          const data = await request<ImportedRun>(
            `/evaluation-runs/${encodeURIComponent(id)}`,
          );
          if (active) setRun(data);
        } else {
          const data = await request<{ items: ImportedRun[] }>(
            "/evaluation-runs",
          );
          if (active) setRuns(data.items);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "读取失败");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [id]);
  if (loading) return <p role="status">正在读取真实运行…</p>;
  if (error)
    return (
      <div className="error" role="alert">
        {error}
      </div>
    );
  if (run) return <ImportedRunDetail run={run} />;
  return (
    <>
      <Header title="评测" desc="查看本地真实运行、逐项评分和可追溯证据。" />
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>真实运行</h2>
            <p>由外部执行后导入，展示真实记录；此页面不会启动模型调用。</p>
          </div>
          <span>{runs.length} 次运行</span>
        </div>
        {runs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>运行</th>
                  <th>项目 / 模型</th>
                  <th>核心验收</th>
                  <th>模型请求</th>
                  <th>估算费用</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.name}</strong>
                      <div className="small muted">
                        {new Date(r.completed_at).toLocaleString("zh-CN")}
                      </div>
                    </td>
                    <td>
                      {r.project_name}
                      <div className="mono muted">{r.model}</div>
                    </td>
                    <td>
                      {r.counts.pass} 通过 / {r.counts.fail} 未通过
                      <div className="small muted">共 {r.case_count} 条</div>
                    </td>
                    <td>{r.requests}</td>
                    <td>US${Number(r.estimated_usd).toFixed(4)}</td>
                    <td>
                      <a className="button" href={`/evaluations/${r.id}`}>
                        查看结果与评测集
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pad muted">尚未导入真实运行。</div>
        )}
      </div>
    </>
  );
}

function mainFinding(runId: string, item: ImportedCase) {
  if (runId === "harness-step30-bailian-20261110" && item.id === "U03") {
    return "停在从复现到动手修复这一步。第 48 次请求确认了旧对话仍在等待输入，到第 60 次达到运行上限时，Agent 还在读临时源码片段，业务源码没有改动。";
  }
  return (
    item.checks.find((c) => c.required_for_task && c.value === 0) ||
    item.checks.find((c) => c.required_for_task && c.value === "unknown") ||
    item.checks.find((c) => c.value === 0)
  )?.reason;
}

function ImportedRunDetail({ run }: { run: ImportedRun }) {
  const [selected, setSelected] = useState(""),
    [filter, setFilter] = useState("全部"),
    [query, setQuery] = useState("");
  const [view, setView] = useState("逐题结果");
  const datasetQuery = new URLSearchParams({
    project: run.project_id,
    draft: run.dataset.draft_id,
  });
  useEffect(() => {
    const selectedId = new URLSearchParams(window.location.search).get("case");
    if (selectedId && run.cases.some((c) => c.id === selectedId))
      setSelected(selectedId);
  }, [run]);
  function choose(id: string) {
    setSelected(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("case", id);
    else url.searchParams.delete("case");
    window.history.replaceState(null, "", url);
  }
  const item = run.cases.find((c) => c.id === selected);
  const visible = run.cases.filter(
    (c) =>
      (filter === "全部" || c.core_acceptance === filter) &&
      `${c.id} ${c.title} ${runCasePresentation(run, c)?.title ?? ""} ${c.group}`.includes(
        query,
      ),
  );
  return (
    <>
      <div className="breadcrumb">
        <a href="/evaluations">真实运行</a> / {run.name}
      </div>
      <Header
        title={run.name}
        desc={`${run.model} · 数据集 v${run.dataset.version} · 单次真实运行`}
        action={
          <a className="button" href={"/datasets?" + datasetQuery}>
            数据集工作区
          </a>
        }
      />
      {!item && (
        <div className="panel pad section-bottom">
          <div className="row" style={{ gap: 28, flexWrap: "wrap" }}>
            <strong>
              {run.counts.pass} / {run.case_count} 核心通过
            </strong>
            <span>{run.counts.fail} 未通过</span>
            <span>{run.requests} 次模型请求</span>
            <span>估算 US${Number(run.estimated_usd).toFixed(4)}</span>
          </div>
          <p style={{ marginTop: 12 }}>{run.summary}</p>
          <details className="small muted">
            <summary>运行用量与评测口径</summary>
            <p>
              {(run.prompt_tokens + run.completion_tokens).toLocaleString()}{" "}
              tokens · {run.method}
            </p>
          </details>
        </div>
      )}
      {item ? (
        <>
          <div className="case-context">
            <button className="button small" onClick={() => choose("")}>
              返回全部 {run.case_count} 条
            </button>
            <label htmlFor="real-case">当前案例</label>
            <select
              id="real-case"
              className="input"
              value={item.id}
              onChange={(e) => choose(e.target.value)}
            >
              {run.cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} · {runCasePresentation(run, c)?.title ?? c.title}
                </option>
              ))}
            </select>
            <span className="small muted">归档验收</span>
            <Badge value={item.core_acceptance} />
          </div>
          <CaseResult key={item.id} run={run} item={item} />
        </>
      ) : (
        <>
          <Tabs
            labels={["逐题结果", "总报告与原始记录"]}
            active={view}
            set={setView}
          />
          {view === "总报告与原始记录" ? (
            <ArtifactViewer
              runId={run.id}
              files={run.files}
              initial="评测结果-20261109.md"
            />
          ) : (
            <div className="panel">
              <div className="toolbar">
                <input
                  className="input"
                  aria-label="搜索真实案例"
                  placeholder="搜索编号、题目或分组"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <select
                  className="input"
                  aria-label="筛选核心验收"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option>全部</option>
                  <option value="pass">核心通过</option>
                  <option value="fail">核心未通过</option>
                </select>
                <span className="small muted">
                  {visible.length} / {run.case_count} 条
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>任务</th>
                      <th>分组 / 难度</th>
                      <th>核心验收</th>
                      <th>主要发现</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((c) => {
                      const presentation = runCasePresentation(run, c);
                      const finding = mainFinding(run.id, c);
                      return (
                        <tr key={c.id}>
                          <td>
                            <button
                              className="button link"
                              onClick={() => choose(c.id)}
                            >
                              {presentation?.title ?? c.title}
                            </button>
                            {presentation && (
                              <p className="small muted">
                                {presentation.summary}
                              </p>
                            )}
                          </td>
                          <td>
                            {c.group}
                            <div className="small muted">
                              {c.difficulty_design}
                            </div>
                          </td>
                          <td>
                            <Badge value={c.core_acceptance} />
                          </td>
                          <td className="small">{finding || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!visible.length && (
                  <p className="pad muted">没有符合筛选条件的案例。</p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function CaseResult({ run, item }: { run: ImportedRun; item: ImportedCase }) {
  const [tab, setTab] = useState("本题结果");
  const presentation = runCasePresentation(run, item);
  const finding = mainFinding(run.id, item);
  const recovery = item.checks.find(
    (c) => c.id === "conflict" && c.value === 1,
  );
  return (
    <div className="section-gap">
      <Header
        title={presentation?.title ?? item.title}
        desc={`${item.group} · ${item.difficulty_design} · ${item.metrics.model_requests} 次请求 · ${item.metrics.elapsed_seconds.toFixed(1)} 秒`}
      />
      {presentation && (
        <div className="panel pad section-bottom">
          {presentation.detail ? (
            <>
              <h2>任务介绍</h2>
              {presentation.detail.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </>
          ) : (
            <>
              <p>{presentation.summary}</p>
              <p>
                <strong>怎样算完成</strong>　{presentation.acceptance}
              </p>
            </>
          )}
        </div>
      )}
      <Tabs
        labels={[
          "本题结果",
          "逐项评分",
          "执行轨迹与交付文件",
          "完整任务与输入",
        ]}
        active={tab}
        set={setTab}
      />
      {tab === "本题结果" ? (
        <div className="panel pad">
          <h2>本题结果</h2>
          <Badge value={item.core_acceptance} />
          {finding && <p>{finding}</p>}
          {recovery && (
            <p>
              <strong>冲突恢复通过</strong>　{recovery.reason}
            </p>
          )}
          <button className="button small" onClick={() => setTab("逐项评分")}>
            查看逐项评分
          </button>{" "}
          <button
            className="button small"
            onClick={() => setTab("执行轨迹与交付文件")}
          >
            查看执行证据
          </button>
        </div>
      ) : tab === "逐项评分" ? (
        <div className="panel pad">
          {dimensions
            .filter((d) => item.checks.some((c) => c.dimension === d))
            .map((d) => (
              <section key={d} style={{ marginBottom: 24 }}>
                <h3>
                  {d}{" "}
                  <span className="small muted">
                    {dimensionLabel(item.dimensions[d])}
                  </span>
                </h3>
                {item.checks
                  .filter((c) => c.dimension === d)
                  .map((c) => (
                    <div className="grade" key={c.id}>
                      <div className="row between">
                        <strong>
                          {c.id} ·{" "}
                          {c.required_for_task ? "核心验收项" : "诊断项"}
                        </strong>
                        <Badge
                          value={
                            c.value === 1
                              ? "pass"
                              : c.value === 0
                                ? "fail"
                                : "missing_evidence"
                          }
                        />
                      </div>
                      <p>{c.rule}</p>
                      <p>{c.reason}</p>
                      <p className="small muted">
                        判据值：{String(c.value)}
                        {c.automatic_value !== undefined
                          ? ` · 原自动值：${String(c.automatic_value)}`
                          : ""}
                      </p>
                      <p className="small">证据：{c.evidence}</p>
                    </div>
                  ))}
              </section>
            ))}
          <button
            className="button"
            onClick={() => setTab("执行轨迹与交付文件")}
          >
            打开原始证据文件
          </button>
          <details style={{ marginTop: 18 }}>
            <summary>Agent 最终答复</summary>
            <pre className="code">{item.final_response}</pre>
          </details>
        </div>
      ) : tab === "完整任务与输入" ? (
        <>
          <div className="panel pad">
            {item.task.turns.map((t) => {
              const sentPrompt = presentation?.sentPrompts?.[t.index];
              return (
                <section key={t.index}>
                  <h3>
                    第 {t.index} 轮 · {t.role}
                  </h3>
                  <pre className="code">{sentPrompt ?? t.content}</pre>
                  {sentPrompt !== undefined && (
                    <details>
                      <summary>运行前题面模板</summary>
                      <pre className="code">{t.content}</pre>
                    </details>
                  )}
                </section>
              );
            })}
            <details>
              <summary>来源、难度依据与控制条件</summary>
              <pre className="code">
                {JSON.stringify(
                  {
                    source: item.task.source,
                    difficulty_basis: item.task.difficulty_basis,
                    controls: item.task.controls,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
          <ArtifactViewer
            runId={run.id}
            files={item.files.filter((f) =>
              f.path.startsWith(`cases/${item.id}/`),
            )}
          />
        </>
      ) : (
        <>
          <TraceNarrative runId={run.id} caseId={item.id} />
          <ArtifactViewer
            runId={run.id}
            files={item.files.filter((f) => !f.path.startsWith("cases/"))}
            initial={`run-20261109/${item.id}/review-evidence.md`}
          />
        </>
      )}
    </div>
  );
}

function ArtifactViewer({
  runId,
  files,
  initial,
}: {
  runId: string;
  files: EvidenceFile[];
  initial?: string;
}) {
  const [path, setPath] = useState(
    files.some((f) => f.path === initial) ? initial! : files[0]?.path || "",
  );
  const [content, setContent] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setContent("");
    setError("");
    if (!path) return;
    setLoading(true);
    fetch(artifactUrl(runId, path), { cache: "no-store" })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok)
          throw new Error(data.error?.message || "文件读取失败");
        return data.content as string;
      })
      .then((text) => {
        if (active) setContent(text);
      })
      .catch((e) => {
        if (active) setError(String(e.message));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [runId, path]);
  const file = files.find((f) => f.path === path);
  return (
    <div className="panel" style={{ marginTop: 20 }}>
      <div className="panel-head">
        <div>
          <h2>原始材料与证据</h2>
          <p>读取时核对 SHA-256；内容按原文展示。</p>
        </div>
        {path && (
          <a className="button small" href={artifactUrl(runId, path, true)}>
            下载原件
          </a>
        )}
      </div>
      <div className="pad">
        <label htmlFor="artifact-path" className="small">
          选择文件（{files.length}）
        </label>
        <select
          id="artifact-path"
          className="input"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          style={{ width: "100%", marginTop: 8 }}
        >
          {files.map((f) => (
            <option key={f.path} value={f.path}>
              {f.path}
            </option>
          ))}
        </select>
        {file && (
          <p
            className="small muted"
            style={{ overflowWrap: "anywhere", marginTop: 10 }}
          >
            {file.bytes.toLocaleString()} 字节 · SHA-256 {file.sha256}
          </p>
        )}
        {loading ? (
          <p role="status">读取中…</p>
        ) : error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          <pre className="code" style={{ maxHeight: 680, overflow: "auto" }}>
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}
