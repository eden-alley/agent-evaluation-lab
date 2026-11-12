"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import type { Comparison } from "../lib/comparisons";
import type { ImportedRun } from "../lib/imported-runs";
import styles from "./comparison-workspace.module.css";

export function ComparisonCreate({
  onCreated,
}: {
  onCreated: (id: string) => void;
}) {
  const [runs, setRuns] = useState<ImportedRun[]>([]),
    [baseline, setBaseline] = useState<ImportedRun | null>(null);
  const [a, setA] = useState(""),
    [b, setB] = useState("missing"),
    [scope, setScope] = useState(""),
    [objective, setObjective] = useState("");
  const [skill, setSkill] = useState<{
    id: string;
    active_version: { id: string; content_hash: string };
  } | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([
      request<{ items: ImportedRun[] }>("/evaluation-runs"),
      request<{
        items: {
          id: string;
          active_version: { id: string; content_hash: string };
        }[];
      }>(
        "/skills?available_only=true&query=" +
          encodeURIComponent("Agent版本对比"),
      ),
    ])
      .then(([r, s]) => {
        if (active) {
          setRuns(r.items);
          setA(r.items[0]?.id ?? "");
          setSkill(s.items[0] ?? null);
        }
      })
      .catch((e) => {
        if (active) setError(String(e.message));
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!a) return;
    let active = true;
    request<ImportedRun>(`/evaluation-runs/${encodeURIComponent(a)}`)
      .then((r) => {
        if (active) {
          setBaseline(r);
          setScope(
            r.cases.some((c) => c.id === "U05-click-default-help")
              ? "U05-click-default-help"
              : (r.cases[0]?.id ?? ""),
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [a]);
  async function create() {
    if (!skill || !baseline) return;
    setBusy(true);
    setError("");
    try {
      const result = await request<Comparison>("/comparisons", {
        method: "POST",
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          name: `${baseline.name} · 版本对比`,
          objective:
            objective ||
            "比较任务表现、执行过程和资源代价，给出有证据的下一步建议。",
          baseline_run_id: a,
          candidate:
            b === "simulation"
              ? { kind: "simulation", fixture_id: "u05-offline-v1" }
              : b === "missing"
                ? { kind: "missing" }
                : { kind: "run", run_id: b },
          case_ids: scope === "all" ? baseline.cases.map((c) => c.id) : [scope],
          workflow: {
            skill_id: skill.id,
            version_id: skill.active_version.id,
            content_hash: skill.active_version.content_hash,
          },
          analyst: {
            kind: "external_agent",
            name: "外部分析Agent（由调用方执行）",
          },
        }),
      });
      onCreated(result.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={styles.form}>
      <h2>准备对比材料</h2>
      <p className={styles.muted}>
        这里只建立材料与题目清单。分析由外部 Agent 发起，不会调用模型。
      </p>
      <div className={styles.split}>
        <div>
          <label htmlFor="compare-a">基线 A</label>
          <select
            id="compare-a"
            className="input"
            value={a}
            onChange={(e) => setA(e.target.value)}
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="compare-b">新版 B</label>
          <select
            id="compare-b"
            className="input"
            value={b}
            onChange={(e) => setB(e.target.value)}
          >
            <option value="missing">尚无新版 · 只整理基线</option>
            <option value="simulation">模拟 B · 仅 U05 离线验证</option>
            {runs
              .filter((r) => r.id !== a)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label htmlFor="compare-scope">本次题目</label>
          <select
            id="compare-scope"
            className="input"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          >
            {baseline?.cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
            <option value="all">基线中的全部题目</option>
          </select>
        </div>
        <div>
          <label htmlFor="compare-objective">本次想检验的改动</label>
          <input
            id="compare-objective"
            className="input"
            value={objective}
            placeholder="例如：通用编辑失败反馈是否改善"
            onChange={(e) => setObjective(e.target.value)}
          />
        </div>
      </div>
      {!skill && <p>版本对比 workflow 尚未发布，请先在内置技能页同步。</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className={styles.actions}>
        <button
          className="button primary"
          disabled={busy || !skill || !scope || !baseline}
          onClick={() => void create()}
        >
          {busy ? "正在准备…" : "创建对比清单"}
        </button>
      </div>
    </div>
  );
}
