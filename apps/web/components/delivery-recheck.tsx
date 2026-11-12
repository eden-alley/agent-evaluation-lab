"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import { artifactUrl } from "../lib/imported-runs";
import type { ImportedRun, ImportedCase } from "../lib/imported-runs";
import { valueLabel } from "../lib/judging";
import { changedChecks, statusLabel } from "../lib/rechecking";
import type { CheckRun, CheckerBinding, CheckerContext } from "../lib/rechecking";
import { Badge } from "./report-ui";
import styles from "./current-capability.module.css";

export function DeliveryRecheck({ run, item }: { run: ImportedRun; item: ImportedCase }) {
  const [context, setContext] = useState<CheckerContext>();
  const [bindingId, setBindingId] = useState("");
  const [selected, setSelected] = useState("");
  const [job, setJob] = useState<CheckRun>();
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = `/evaluation-runs/${encodeURIComponent(run.id)}`;
  const caseBase = `${base}/cases/${encodeURIComponent(item.id)}`;
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const next = await request<CheckerContext>(caseBase + "/checker");
        if (!active) return;
        setContext(next);
        const id = selected || next.runs[0]?.id;
        if (id) {
          const saved = await request<CheckRun>(base + "/check-runs/" + encodeURIComponent(id));
          if (!active) return;
          setJob(saved);
        } else setJob(undefined);
        setError("");
        if (next.runs.some(row => row.status === "queued" || row.status === "running"))
          timer = setTimeout(load, 1000);
      } catch (e) {
        if (active) {
          setError((e as Error).message + " 正在重新连接，也可以手动刷新。");
          timer = setTimeout(load, 5000);
        }
      }
    }
    void load();
    return () => { active = false; clearTimeout(timer); };
  }, [base, caseBase, selected, refresh]);

  if (!context || !context.available.length) return error ? <p role="alert">{error}</p> : null;
  const currentBinding = context.bindings.find(b => b.id === bindingId) || context.bindings[0];
  async function associate() {
    setBusy(true); setError("");
    try {
      const checker = context!.available[0];
      const saved = await request<CheckerBinding>(caseBase + "/checker-bindings", {
        method: "POST", body: JSON.stringify({ request_id: crypto.randomUUID(),
          package_id: checker.id, package_version: checker.version }),
      });
      setBindingId(saved.id); setRefresh(n => n + 1);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function checkAgain() {
    if (!currentBinding) return;
    setBusy(true); setError("");
    try {
      const saved = await request<CheckRun>(base + "/check-runs", {
        method: "POST", body: JSON.stringify({ request_id: crypto.randomUUID(), binding_id: currentBinding.id }),
      });
      setSelected(saved.id); setJob(saved); setRefresh(n => n + 1);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const report = job?.report;
  const changes = changedChecks(report?.checks ?? []);
  return <section className="panel pad section-bottom" aria-label="检查程序与重新检查">
    <div className={styles.heading}>
      <div><h2>检查程序与重新检查</h2>
        <p className="small muted">用保存的代码独立验收，不重新运行 Agent。原归档成绩和复核记录继续保留。</p></div>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <button className="button" disabled={busy} onClick={() => void associate()}>
          {currentBinding ? "重新关联检查程序" : "关联检查程序"}</button>
        <button className="button primary" disabled={busy || !currentBinding} onClick={() => void checkAgain()}>
          {busy ? "处理中…" : "重新检查旧交付"}</button>
      </div>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {currentBinding ? <>
      <p>已关联：<strong>{currentBinding.snapshot.package.name}</strong> · v{currentBinding.snapshot.package.version}</p>
      {context.bindings.length > 1 && <label className={styles.selector}>本次使用的检查配置
        <select className="input" value={currentBinding.id} onChange={e => setBindingId(e.target.value)}>
          {context.bindings.map(b => <option key={b.id} value={b.id}>{b.created_at.slice(0, 19)} · v{b.snapshot.package.version}</option>)}
        </select></label>}
    </> : <p className="muted">先为本题关联固定版本的检查程序，再检查已保存的交付物。</p>}
    {context.runs.length > 0 && <label className={styles.selector}>独立检查记录
      <select className="input" value={selected || context.runs[0].id}
        onChange={e => { setJob(undefined); setError(""); setSelected(e.target.value); }}>
        {context.runs.map(row => <option key={row.id} value={row.id}>
          {row.created_at.slice(0, 19)} · {statusLabel(row.status)}
        </option>)}
      </select></label>}
    {job && <p role="status">{statusLabel(job.status)}</p>}
    {job?.source_warning && <p role="alert">{job.source_warning}</p>}
    {job?.error && <p role="alert">检查程序未完成：{job.error.message}。这次没有产生新的 Agent 成绩。</p>}
    {report && <>
      <div className={styles.context}><strong>旧交付物的本次验收</strong><Badge value={report.core_acceptance} />
        <span>新增模型请求：{report.agent_model_requests + report.judge_model_requests}</span>
        <span>原 Agent 执行仍为 {report.original_model_requests} 次请求</span></div>
      <p className="small muted">本次重新检查产生了新的测试证据；“当时是否自测”等过程项只依据原始记录判断。</p>
      {changes.length > 0 && <p>{changes.length} 项判定与历史记录不同。差异来自检查方法或证据范围，不表示 Agent 能力发生变化。</p>}
      <div className="table-wrap"><table>
        <thead><tr><th>检查内容</th><th>历史判定</th><th>本次判定</th><th>依据</th></tr></thead>
        <tbody>{report.checks.map(check => <tr key={check.id}>
          <td>{check.rule}<div className="small muted">{check.required_for_task ? "任务要求" : "诊断项"}</div></td>
          <td>{valueLabel(check.historical_value)}</td><td>{valueLabel(check.value)}</td>
          <td><p>{check.reason}</p><details><summary>查看依据</summary>
            {check.evidence.map(path => <p key={path}><a target="_blank" rel="noreferrer"
              href={report.evidence.some(e => e.path === path)
                ? `/api/v1${base}/check-runs/${job.id}/artifact?path=${encodeURIComponent(path)}`
                : artifactUrl(run.id, path)}>{path.endsWith("public.json") ? "本次公开测试结果" :
                  path.endsWith("external.json") ? "本次独立测试结果" : path.split("/").at(-1)}</a></p>)}
          </details></td>
        </tr>)}</tbody>
      </table></div>
      <details className={styles.boundary}><summary>任务、检查程序与环境版本</summary>
        <p>原执行：{run.id} / {item.id}</p>
        <p>检查程序：{report.binding.package.name} · v{report.binding.package.version}</p>
        <p>任务内容摘要：{report.binding.task.content_hash}</p>
        <p>检查程序摘要：{report.binding.package.content_hash}</p>
        <p>输入摘要：{report.binding.input_hash}</p>
        <p>执行环境：{report.binding.environment.backend} · {report.binding.environment.python_version ?? report.binding.environment.python}</p>
      </details>
    </>}
  </section>;
}
