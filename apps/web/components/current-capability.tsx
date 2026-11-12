"use client";
import { useEffect, useRef, useState } from "react";
import { request } from "../lib/api";
import { artifactUrl } from "../lib/imported-runs";
import type { ImportedRun } from "../lib/imported-runs";
import type { GradeValue, JudgeCheck, JudgeEvidence, Judgment } from "../lib/judging";
import { groupFindings, reviewLabels, valueLabel } from "../lib/judging";
import { Badge } from "./report-ui";
import styles from "./current-capability.module.css";

type JobSummary = Pick<Judgment, "id" | "mode" | "status" | "created_at">;

function Evidence({ runId, evidence }: { runId: string; evidence: JudgeEvidence[] }) {
  const [selected, setSelected] = useState(0);
  const [full, setFull] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  const current = evidence[selected];
  async function loadFull() {
    const ticket = ++generation.current;
    setBusy(true); setError("");
    try {
      const response = await request<{ content: string }>(
        `/evaluation-runs/${encodeURIComponent(runId)}/artifact?path=${encodeURIComponent(current.path)}`);
      if (ticket === generation.current) setFull(response.content);
    } catch (e) { if (ticket === generation.current) setError((e as Error).message); }
    finally { if (ticket === generation.current) setBusy(false); }
  }
  if (!current) return <p className="small muted">归档没有可定位证据。</p>;
  return <details className={styles.evidence}>
    <summary>查看证据 · {evidence.length} 份原始记录</summary>
    <div className={styles.evidenceBody}>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        {evidence.map((ref, index) => <button key={ref.path} className="button small"
          aria-pressed={selected === index} onClick={() => { generation.current += 1; setBusy(false); setSelected(index); setFull(undefined); setError(""); }}>
          {ref.label}
        </button>)}
      </div>
      <p className="small muted">{current.path}</p>
      {error && <p role="alert">{error}</p>}
      <pre className={"code " + styles.excerpt}>{full ?? current.excerpt}</pre>
      {current.truncated && !full && <button className="button small" disabled={busy} onClick={loadFull}>
        {busy ? "读取中…" : "读取完整证据"}
      </button>}
      <a className="button small" href={artifactUrl(runId, current.path, true)}>下载原始记录</a>
    </div>
  </details>;
}

function ReviewForm({ runId, job, caseId, check, onSaved }: {
  runId: string; job: Judgment; caseId: string; check: JudgeCheck; onSaved: (job: Judgment) => void;
}) {
  const [value, setValue] = useState<GradeValue>(check.judge_value ?? "unknown");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestId = useRef("");
  function edited() { requestId.current = ""; }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    if (!requestId.current) requestId.current = crypto.randomUUID();
    try {
      const data = await request<Judgment>(
        `/evaluation-runs/${encodeURIComponent(runId)}/judgments/${job.id}/reviews`,
        { method: "POST", body: JSON.stringify({ request_id: requestId.current, case_id: caseId,
          check_id: check.id, value, reason, revision: job.revision }) });
      onSaved(data); requestId.current = "";
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <form className={styles.review} onSubmit={save}>
    <label>人工终判
      <select className="input" value={String(value)} onChange={e =>
        { edited(); setValue(e.target.value === "unknown" ? "unknown" : Number(e.target.value) as 0 | 1); }}>
        <option value="1">通过</option><option value="0">未通过</option><option value="unknown">证据不足</option>
      </select>
    </label>
    <label>复核依据<textarea className="input" required maxLength={12000} value={reason}
      onChange={e => { edited(); setReason(e.target.value); }} placeholder="说明依据哪份材料确认或修正判定" /></label>
    {error && <p role="alert">{error}</p>}
    {error && <button type="button" className="button" onClick={async () => {
      try { onSaved(await request<Judgment>(
        `/evaluation-runs/${encodeURIComponent(runId)}/judgments/${job.id}`)); setError(""); edited(); }
      catch (e) { setError((e as Error).message); }
    }}>刷新报告后继续复核</button>}
    <button className="button primary" disabled={busy}>{busy ? "保存中…" : "保存人工复核"}</button>
  </form>;
}

export function CurrentCapability({ run, caseId, onChoose }: {
  run: ImportedRun; caseId?: string; onChoose?: (id: string) => void;
}) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [job, setJob] = useState<Judgment>();
  const [error, setError] = useState("");
  const base = `/evaluation-runs/${encodeURIComponent(run.id)}/judgments`;
  useEffect(() => {
    let active = true;
    request<{ items: JobSummary[] }>(base).then(data => {
      if (!active) return;
      setJobs(data.items);
      const requested = new URLSearchParams(window.location.search).get("judgment");
      const choice = data.items.find(j => j.id === requested) ??
        data.items.find(j => j.mode === "archive" && j.status === "completed") ?? data.items[0];
      setSelected(choice?.id ?? "");
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [base]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setJob(undefined); setError("");
    async function load() {
      try {
        const data = await request<Judgment>(base + "/" + selected);
        if (!active) return;
        setJob(data);
        if (["queued", "running"].includes(data.status)) timer = setTimeout(load, 1200);
      } catch (e) { if (active) setError((e as Error).message); }
    }
    load();
    return () => { active = false; clearTimeout(timer); };
  }, [base, selected]);
  function selectJob(id: string) {
    setSelected(id);
    const url = new URL(window.location.href); url.searchParams.set("judgment", id);
    window.history.replaceState(null, "", url);
  }
  const report = job?.report;
  const cases = report?.cases.filter(c => !caseId || c.id === caseId) ?? [];
  const findings = report?.findings.filter(f => !caseId || f.case_id === caseId) ?? [];
  const groups = groupFindings(findings);
  const missing = cases.flatMap(c => c.checks.filter(check => check.applicable &&
    check.value === "unknown" && check.review_state !== "pending").map(check => ({ caseId: c.id, check })));
  const pass = cases.filter(c => c.core_acceptance === "pass").length;
  const fail = cases.filter(c => c.core_acceptance === "fail").length;
  return <section className={styles.page} aria-label={caseId ? "本题评审与复核" : "当前能力"}>
    <div className={styles.heading}>
      <div><h2>{caseId ? "本题评审与复核" : "当前能力"}</h2>
        <p className="muted small">{caseId ? "逐项核对判定来源和证据。" : "先看暴露的问题，再看涉及的题目与证据。"}</p></div>
      {jobs.length > 0 && <label className={styles.selector}>评审记录
        <select className="input" value={selected} onChange={e => selectJob(e.target.value)}>
          {jobs.map(j => <option key={j.id} value={j.id}>
            {j.mode === "archive" ? "真实归档 · 历史判定" : "模拟 Judge · 离线验证"} · {j.created_at.slice(0, 16)}
          </option>)}
        </select>
      </label>}
    </div>
    {error && <p role="alert">{error}</p>}
    {!jobs.length && !error && <p className="muted">尚无独立评审记录。Coding Agent 可通过 MCP 发起归档整理或模拟评审。</p>}
    {job?.status === "failed" && <p role="alert">评审执行异常 · {job.error?.message}。可使用新的请求编号重新发起。</p>}
    {job && ["queued", "running"].includes(job.status) && <p role="status">评审处理中…</p>}
    {report && <>
      <div className={report.is_simulation ? "preview" : styles.context}>
        <strong>{report.is_simulation ? "模拟 Judge · 离线验证" : "真实归档 · 历史判定整理"}</strong>
        <span>{report.provenance} · 新模型请求 {report.model_requests}</span>
      </div>
      {!cases.length ? <p>这份报告的评审范围未包含本题。</p> : <>
        <div className={styles.counts}>
          <span><strong>{cases.length}</strong> 道题</span>
          <span><strong>{pass}</strong> 核心通过</span>
          <span><strong>{fail}</strong> 核心未通过</span>
          <span><strong>{cases.length - pass - fail}</strong> 尚待确认</span>
        </div>
        {caseId ? cases.map(c => <div key={c.id}>
          <p><Badge value={c.core_acceptance === "unknown" ? "missing_evidence" : c.core_acceptance} /></p>
          {c.checks.map(check => <details key={check.id} className={styles.check}>
            <summary><strong>{check.id} · {check.rule}</strong>
              <span className={styles.state}>{reviewLabels[check.review_state]} · {valueLabel(check.value)}</span></summary>
            <div className={styles.body}>
              <p>{check.reason}</p>
              <p className="small">原自动值 {valueLabel(check.automatic_value)} → Judge 建议 {valueLabel(check.judge_value)} → 生效值 {valueLabel(check.value)}</p>
              <p className="small muted">来源 · {check.source}</p>
              <p className="small muted">证据状态 · {check.evidence_state === "inherited" ? "引用历史判定，未独立重验" :
                check.evidence_state === "simulated" ? "模拟响应" :
                check.evidence_state === "insufficient" ? "证据不足" :
                check.evidence_state === "conflict" ? "存在判定分歧" : "复核已确认"}</p>
              {check.review_reason && <p>{check.review_reason}</p>}
              <Evidence runId={run.id} evidence={check.evidence} />
              {check.applicable && job && <details>
                <summary>{check.review_state === "pending" ? "处理待复核项" : "人工追加复核"}</summary>
                <ReviewForm runId={run.id} job={job} caseId={c.id} check={check} onSaved={setJob} />
              </details>}
            </div>
          </details>)}
        </div>) : [
          ["core", "影响任务完成"], ["diagnostic", "其他诊断线索"],
          ["unresolved", "等待确认"], ["evaluator", "评测质量"]
        ].map(([owner, title]) => {
          const owned = groups.filter(g =>
            owner === "core" ? g.owner === "agent" && g.items.some(i => i.required_for_task) :
            owner === "diagnostic" ? g.owner === "agent" && !g.items.some(i => i.required_for_task) :
            g.owner === owner);
          if (!owned.length) return null;
          return <section key={owner} className={styles.group}>
            <h3>{title}</h3>
            {owned.map(group => <details key={group.title} className={styles.finding}>
              <summary><strong>{group.title}</strong>
                <span className={styles.state}>{new Set(group.items.map(i => i.case_id)).size} 道题 ·
                  {group.items.length === 1 ? "单题观察" : "展开查看"}</span></summary>
              <div className={styles.body}>
                {group.items.map(item => <div className={styles.case} key={item.case_id + item.check_id}>
                  <button className="button link" onClick={() => onChoose?.(item.case_id)}>
                    {item.case_id} · {cases.find(c => c.id === item.case_id)?.title}
                  </button>
                  <p>{item.phenomenon}</p>
                  <p className="small muted">{item.required_for_task ? "核心验收项" : "诊断项"} · {item.check_id}</p>
                  <Evidence runId={run.id} evidence={item.evidence} />
                </div>)}
              </div>
            </details>)}
          </section>;
        })}
        {!caseId && missing.length > 0 && <details className={styles.finding}>
          <summary>证据不足 · {missing.length} 项检查</summary>
          <div className={styles.body}>{missing.map(item => <p key={item.caseId + item.check.id}>
            <strong>{item.caseId} / {item.check.id}</strong> · {item.check.reason}</p>)}</div>
        </details>}
        {!caseId && !groups.length && <p>本次评审范围内暂未记录缺陷或待复核项。</p>}
        {job.reviews.length > 0 && <details className={styles.boundary}>
          <summary>人工复核记录 · {job.reviews.length} 次</summary>
          {job.reviews.filter(r => !caseId || r.case_id === caseId).map(r => <p key={r.revision}>
            第 {r.revision} 次 · {r.case_id} / {r.check_id} · {valueLabel(r.value)} · {r.reason}
          </p>)}
        </details>}
        <details className={styles.boundary}><summary>证据范围与评分版本</summary>
          <p>本页描述本次案例的观察。每题的单次结果用于发现线索，跨任务泛化和重复运行稳定性需要额外证据。不同线索可能涉及同一道题。</p>
          <p className="small">格式 v{report.schema_version} · Skill 版本 {report.skill.version_id} · 内容哈希 {report.skill.content_hash}</p>
        </details>
      </>}
    </>}
  </section>;
}

