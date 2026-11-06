"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, FileCheck2 } from "lucide-react";
import { qualityApi } from "../lib/quality-api";
import type {
  DatasetDraft,
  DatasetVersion,
  EvidenceRef,
  QualityReport,
  Source,
} from "../lib/quality-types";
import { Metric, Tabs, json } from "./report-ui";

const severityLabel = { blocker: "阻断", warning: "待确认", info: "提示" };
const coverageLabel = {
  covered: "已覆盖",
  partial: "部分覆盖",
  missing: "缺少覆盖",
  not_assessed: "未检查",
};
const fieldLabel: Record<string, string> = {
  input: "输入",
  expected: "预期结果",
  title: "标题",
  grading_notes: "评分说明",
  requirement_ids: "关联需求",
  description: "需求描述",
  task_description: "任务目标",
};

export function SourceInfo({ source }: { source: Source }) {
  return (
    <div className="stack">
      <p className="small muted">客户端声明：{source.client}</p>
      {source.skills.length ? (
        source.skills.map((ref) => (
          <div className="source-ref" key={ref.version_id}>
            <a
              className="click"
              href={"/skills?skill=" + encodeURIComponent(ref.skill_id)}
            >
              {ref.skill_id} <ArrowUpRight size={12} className="inline-icon" />
            </a>
            <p className="mono break-word">版本：{ref.version_id}</p>
            <p className="mono muted break-word">{ref.content_hash}</p>
          </div>
        ))
      ) : (
        <p className="small muted">未关联平台内的技能版本。</p>
      )}
      {source.skill_name && (
        <p className="small muted">
          外部自报技能：{source.skill_name} {source.skill_version || ""}
          （未作平台版本验证）
        </p>
      )}
    </div>
  );
}

export function QualityDetail({
  draft,
  version,
  onChange,
  onBack,
  onBusy,
}: {
  draft: DatasetDraft;
  version?: DatasetVersion;
  onChange: (draft: DatasetDraft) => void;
  onBack: () => void;
  onBusy: (busy: boolean) => void;
}) {
  const [tab, setTab] = useState("质量报告"),
    [report, setReport] = useState<QualityReport | null>(draft.latest_report);
  const [caseId, setCaseId] = useState(draft.payload.cases[0]?.case_id),
    [highlight, setHighlight] = useState<EvidenceRef | null>(null);
  const [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [reportLoading, setReportLoading] = useState(false);
  const reportEpoch = useRef(0),
    detailRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setReport(draft.latest_report);
  }, [draft.latest_report]);
  useEffect(() => {
    if (highlight && tab === "用例与需求") {
      detailRef.current?.scrollIntoView({ block: "center" });
      detailRef.current?.focus();
    }
  }, [highlight, tab]);
  const m = draft.metrics,
    current = draft.latest_report;
  const historical = !!report && report.id !== current?.id;
  const blocked =
    !current ||
    m.reviewed_cases !== m.total_cases ||
    m.blockers > 0 ||
    historical ||
    reportLoading;
  const needsNote =
    m.warnings > 0 ||
    current?.payload.coverage.some((c) => c.status !== "covered");
  const chosen =
    draft.payload.cases.find((c) => c.case_id === caseId) ||
    draft.payload.cases[0];
  function evidence(ref: EvidenceRef) {
    if (ref.target_type === "case" && ref.target_id) setCaseId(ref.target_id);
    setHighlight(ref);
    setTab("用例与需求");
  }
  async function loadReport(id: string) {
    const request = ++reportEpoch.current;
    setReportLoading(true);
    setError("");
    try {
      const next =
        id === current?.id ? current : await qualityApi.report(draft.id, id);
      if (request === reportEpoch.current) setReport(next);
    } catch (e) {
      if (request === reportEpoch.current)
        setError(e instanceof Error ? e.message : "报告加载失败");
    } finally {
      if (request === reportEpoch.current) setReportLoading(false);
    }
  }
  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const next = await qualityApi.decide(
        draft.id,
        decision,
        current?.id || null,
        note,
      );
      onChange(next.draft);
      setNote("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "审阅未完成");
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }
  const focusValue =
    highlight?.target_type === "task"
      ? draft.payload.task_description
      : highlight?.target_type === "requirement"
        ? draft.payload.requirements.find((r) => r.id === highlight.target_id)
            ?.description
        : highlight && chosen
          ? (chosen as unknown as Record<string, unknown>)[highlight.field]
          : undefined;
  return (
    <>
      <div className="breadcrumb">
        <button className="button link small" disabled={busy} onClick={onBack}>
          <ArrowLeft size={14} />
          返回数据集列表
        </button>
      </div>
      <div className="page-head">
        <div>
          <h1>{draft.payload.name}</h1>
          <p>
            {version ? `固定版本 v${version.version}` : "评测集草案"} ·{" "}
            {new Date(draft.created_at).toLocaleString("zh-CN")}
          </p>
        </div>
        <span
          className={
            "badge " +
            (draft.status === "approved"
              ? "good"
              : draft.status === "rejected"
                ? "bad"
                : "warn")
          }
        >
          {draft.status === "approved"
            ? "人工已确认"
            : draft.status === "rejected"
              ? "已退回"
              : "等待审阅"}
        </span>
      </div>
      <div className="metrics">
        <Metric label="用例总数" value={m.total_cases} />
        <Metric
          label="程序校验"
          value={`${m.structurally_checked_cases}/${m.total_cases}`}
          note="仅格式与确定性检查"
        />
        <Metric
          label="外部报告已检查"
          value={`${m.reviewed_cases}/${m.total_cases}`}
        />
        <Metric
          label="报告声明需求覆盖"
          value={`${m.covered_requirements}/${m.requirements}`}
        />
        <Metric label="阻断 / 待确认" value={`${m.blockers} / ${m.warnings}`} />
      </div>
      <div className="run-tabs">
        <Tabs
          labels={["质量报告", "用例与需求", "版本与来源"]}
          active={tab}
          set={setTab}
        />
      </div>
      {error && (
        <div role="alert" className="error section-bottom">
          {error}{" "}
          <button
            className="button small"
            disabled={busy}
            onClick={async () => {
              try {
                onChange(await qualityApi.draft(draft.id));
                setError("");
              } catch (e) {
                setError(e instanceof Error ? e.message : "刷新失败");
              }
            }}
          >
            刷新草案
          </button>
        </div>
      )}
      {tab === "质量报告" && (
        <>
          <div className="panel section-bottom">
            <div className="panel-head">
              <div>
                <h2>程序校验</h2>
                <p>只判断结构、精确重复与引用完整性，不替代语义质量检查。</p>
              </div>
              <span
                className={"badge " + (draft.checks.length ? "warn" : "good")}
              >
                {draft.checks.length} 项发现
              </span>
            </div>
            <div className="pad stack">
              {draft.checks.length ? (
                draft.checks.map((check) => (
                  <div className="quality-finding" key={check.id}>
                    <div className="row">
                      <span
                        className={
                          "badge " +
                          (check.severity === "blocker" ? "bad" : "warn")
                        }
                      >
                        {severityLabel[check.severity]}
                      </span>
                      <strong>{check.message}</strong>
                    </div>
                    <div className="row small">
                      {check.case_ids.map((id) => (
                        <button
                          className="button link small"
                          key={id}
                          onClick={() => {
                            setCaseId(id);
                            setHighlight(null);
                            setTab("用例与需求");
                          }}
                        >
                          案例 {id}
                        </button>
                      ))}
                      {check.requirement_ids.map((id) => (
                        <button
                          className="button link small"
                          key={id}
                          onClick={() =>
                            evidence({
                              target_type: "requirement",
                              target_id: id,
                              field: "description",
                              quote: "",
                            })
                          }
                        >
                          需求 {id}
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="small muted">
                  未发现当前程序规则能够识别的问题。语义覆盖与预期结果依据仍需审阅。
                </p>
              )}
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <div>
                <h2>外部质量报告</h2>
                <p>保留调用方判断与引用依据，结论由你审阅。</p>
              </div>
              {draft.report_history.length > 0 && (
                <select
                  aria-label="质量报告版本"
                  className="input compact-select"
                  value={report?.id || ""}
                  disabled={busy || reportLoading}
                  onChange={(e) => loadReport(e.target.value)}
                >
                  {draft.report_history.map((r) => (
                    <option key={r.id} value={r.id}>
                      报告 #{r.sequence}
                      {r.id === current?.id ? " · 最新" : " · 历史"}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {reportLoading ? (
              <p className="pad muted">正在读取报告…</p>
            ) : !report ? (
              <div className="empty">
                <FileCheck2 className="empty-icon" size={28} />
                <h2>等待外部检查结果</h2>
                <p>
                  外部 Coding Agent
                  读取草案后，通过提交质量报告工具交付检查范围与证据。
                </p>
              </div>
            ) : (
              <div className="pad stack">
                {historical && (
                  <div className="notice">
                    正在查看历史报告 #{report.sequence}
                    ；上方汇总仍对应最新报告。请切回最新报告再确认版本。
                  </div>
                )}
                <p className="quality-summary">{report.payload.summary}</p>
                <p className="small muted">
                  报告 #{report.sequence} · {report.payload.source.client} ·
                  已检查 {report.payload.reviewed_case_ids.length}/
                  {m.total_cases} 条
                </p>
                <div className="table-wrap">
                  <table className="coverage-table">
                    <thead>
                      <tr>
                        <th>需求</th>
                        <th>外部判断</th>
                        <th>关联案例</th>
                        <th>理由</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.payload.coverage.map((c) => (
                        <tr key={c.requirement_id}>
                          <td>
                            <button
                              className="button link small"
                              onClick={() =>
                                evidence({
                                  target_type: "requirement",
                                  target_id: c.requirement_id,
                                  field: "description",
                                  quote: "",
                                })
                              }
                            >
                              {c.requirement_id}
                            </button>
                          </td>
                          <td>
                            <span
                              className={
                                "badge " +
                                (c.status === "covered" ? "good" : "warn")
                              }
                            >
                              {coverageLabel[c.status]}
                            </span>
                          </td>
                          <td>
                            {c.case_ids.length
                              ? c.case_ids.map((id) => (
                                  <button
                                    className="button link small"
                                    key={id}
                                    onClick={() => {
                                      setCaseId(id);
                                      setHighlight(null);
                                      setTab("用例与需求");
                                    }}
                                  >
                                    {id}
                                  </button>
                                ))
                              : "—"}
                          </td>
                          <td className="wrap-text">{c.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h3>质量问题 · {report.payload.findings.length} 项</h3>
                {!report.payload.findings.length && (
                  <p className="small muted">
                    报告未提出质量问题。这是提交方的判断，不等于独立质量保证。
                  </p>
                )}
                {report.payload.findings.map((f) => (
                  <article className="quality-finding" key={f.id}>
                    <div className="row">
                      <span
                        className={
                          "badge " +
                          (f.severity === "blocker"
                            ? "bad"
                            : f.severity === "warning"
                              ? "warn"
                              : "info")
                        }
                      >
                        {severityLabel[f.severity]}
                      </span>
                      <strong>{f.explanation}</strong>
                    </div>
                    <p className="small muted section-note">
                      建议：{f.suggestion}
                    </p>
                    {f.evidence.map((ev, i) => (
                      <div className="evidence-quote" key={i}>
                        <blockquote>{ev.quote}</blockquote>
                        <button
                          className="button link small"
                          onClick={() => evidence(ev)}
                        >
                          定位 {ev.target_id || "任务目标"} ·{" "}
                          {fieldLabel[ev.field] || ev.field}{" "}
                          <ArrowUpRight size={12} />
                        </button>
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            )}
          </div>
        </>
      )}
      {tab === "用例与需求" && (
        <div className="stack">
          <div className="panel pad stack">
            <h2>任务与需求</h2>
            <p>{draft.payload.task_description}</p>
            {draft.payload.requirements.map((r) => (
              <div className="requirement-row" key={r.id}>
                <strong className="mono">{r.id}</strong>
                <span>{r.description}</span>
              </div>
            ))}
          </div>
          {highlight && (
            <div
              className="notice evidence-focus"
              ref={detailRef}
              tabIndex={-1}
            >
              <strong>
                定位证据：{highlight.target_id || "任务目标"} ·{" "}
                {fieldLabel[highlight.field]}
              </strong>
              {highlight.quote && <blockquote>{highlight.quote}</blockquote>}
              <pre className="code">{json(focusValue)}</pre>
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <div>
                <h2>案例内容</h2>
                <p>原始提交内容不可原地覆盖；修订需要提交新草案。</p>
              </div>
              <select
                aria-label="查看案例"
                className="input compact-select"
                value={caseId}
                onChange={(e) => {
                  setCaseId(e.target.value);
                  setHighlight(null);
                }}
              >
                {draft.payload.cases.map((c) => (
                  <option key={c.case_id} value={c.case_id}>
                    {c.case_id} · {c.title}
                  </option>
                ))}
              </select>
            </div>
            {chosen && (
              <div className="pad stack">
                <div className="row between">
                  <h3>{chosen.title}</h3>
                  <span className="small muted">
                    需求：{chosen.requirement_ids.join("、") || "未关联"}
                  </span>
                </div>
                <div className="split">
                  <div>
                    <h3>输入</h3>
                    <pre className="code">{json(chosen.input)}</pre>
                  </div>
                  <div>
                    <h3>预期结果</h3>
                    <pre className="code">{json(chosen.expected)}</pre>
                  </div>
                </div>
                <div>
                  <h3>评分说明</h3>
                  <p className="section-note">
                    {chosen.grading_notes || "未提供"}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {tab === "版本与来源" && (
        <div className="panel pad stack">
          <h2>生成来源与内容绑定</h2>
          <SourceInfo source={draft.payload.source} />
          <div>
            <h3>内容哈希</h3>
            <p className="mono break-word section-note">{draft.content_hash}</p>
          </div>
          <div>
            <h3>基准版本</h3>
            <p className="mono break-word section-note">
              {draft.payload.base_version_id || "首次创建"}
            </p>
          </div>
          {current && (
            <>
              <h3>质量报告来源</h3>
              <SourceInfo source={current.payload.source} />
            </>
          )}
          <p className="small muted">
            技能引用验证版本与哈希存在，不证明外部 Agent 确实遵循了其中的方法。
          </p>
        </div>
      )}
      {draft.status === "pending" && !version ? (
        <div className="panel section-gap">
          <div className="panel-head">
            <div>
              <h2>审阅结论</h2>
              <p>确认后生成固定版本，保留本次内容、最新报告与来源。</p>
            </div>
          </div>
          <div className="pad stack">
            <div className="field">
              <label htmlFor="review-note">
                审阅说明{needsNote ? "（存在警告或覆盖缺口，确认时必填）" : ""}
              </label>
              <textarea
                id="review-note"
                className="input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                disabled={busy}
                placeholder="记录接受限制或退回修改的原因"
              />
            </div>
            <div className="row">
              <button
                className="button primary"
                disabled={busy || blocked || (!!needsNote && !note.trim())}
                onClick={() => decide("approve")}
              >
                {busy ? "处理中…" : "确认生成版本"}
              </button>
              <button
                className="button"
                disabled={busy || reportLoading || historical || !note.trim()}
                onClick={() => decide("reject")}
              >
                退回修改
              </button>
              {blocked && (
                <span className="small muted">
                  {historical
                    ? "请切回最新报告"
                    : !current
                      ? "等待质量报告"
                      : m.blockers
                        ? "请先修订阻断问题"
                        : "全部案例检查完成后可确认"}
                </span>
              )}
            </div>
          </div>
        </div>
      ) : (
        draft.decision && (
          <div className="notice section-gap">
            <strong>
              {draft.status === "approved" ? "已人工确认" : "已退回修改"}
            </strong>
            <p>{draft.decision.note || "未附加说明"}</p>
            <p className="small muted">
              {new Date(draft.decision.decided_at).toLocaleString("zh-CN")}
            </p>
          </div>
        )
      )}
    </>
  );
}
