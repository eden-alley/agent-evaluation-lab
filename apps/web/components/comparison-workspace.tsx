"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/api";
import type { Comparison } from "../lib/comparisons";
import { comparisonPath, demonstration } from "../lib/comparisons";
import { Header } from "./report-ui";
import { ComparisonCreate } from "./comparison-create";
import { ComparisonReportView } from "./comparison-report";
import styles from "./comparison-workspace.module.css";

export function ComparisonWorkspace() {
  const [items, setItems] = useState<Comparison[]>([]),
    [selected, setSelected] = useState(""),
    [detail, setDetail] = useState<Comparison | null>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [showCreate, setShowCreate] = useState(false),
    [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    request<{ items: Comparison[] }>("/comparisons")
      .then((r) => {
        if (active) {
          setItems(r.items);
          const id = new URLSearchParams(window.location.search).get(
            "comparison",
          );
          if (id) setSelected(id);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reload]);
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let active = true;
    setError("");
    setDetail(null);
    request<Comparison>(comparisonPath(selected))
      .then((r) => {
        if (active) setDetail(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [selected, reload]);
  function choose(id: string) {
    setSelected(id);
    setShowCreate(false);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("comparison", id);
    else url.searchParams.delete("comparison");
    url.searchParams.delete("case");
    window.history.replaceState(null, "", url);
    setReload((v) => v + 1);
  }
  return (
    <div className={styles.workspace}>
      {(!selected || showCreate) && (
        <Header
          title="版本对比"
          desc="对照真实记录，查看表现变化、证据与下一步开发方向。"
          action={
            <button
              className="button primary"
              onClick={() => setShowCreate((v) => !v)}
            >
              {showCreate ? "收起创建" : "准备新对比"}
            </button>
          }
        />
      )}
      {showCreate && <ComparisonCreate onCreated={choose} />}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {loading ? (
        <p role="status">正在读取对比报告…</p>
      ) : selected ? (
        <>
          <div className={styles.topline}>
            <button className="button small" onClick={() => choose("")}>
              返回全部对比
            </button>
            <button
              className="button small"
              onClick={() => setReload((v) => v + 1)}
            >
              刷新收到的分析
            </button>
          </div>
          {detail ? (
            <ComparisonReportView key={detail.id} comparison={detail} />
          ) : (
            !error && <p role="status">正在读取报告…</p>
          )}
        </>
      ) : items.length ? (
        <div className={styles.list}>
          {items.map((item) => (
            <div className={styles.item} key={item.id}>
              <div className={styles.row}>
                <span className={styles.tag}>
                  {demonstration(item) ? "离线模拟验证" : "外部分析"}
                </span>
                <span className={styles.muted}>
                  {new Date(item.created_at).toLocaleString("zh-CN")}
                </span>
              </div>
              <h3>{item.name}</h3>
              <p className={styles.muted}>
                {item.baseline.name} → {item.candidate?.name ?? "等待新版记录"}
              </p>
              <div className={styles.row}>
                <span>
                  逐题记录 {item.progress.received}/{item.progress.planned} ·{" "}
                  {item.reports.length ? "已有对比报告" : "等待外部分析"}
                </span>
                <button className="button" onClick={() => choose(item.id)}>
                  查看对比与开发建议
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.intro}>
          <h2>先准备一组前后材料</h2>
          <p>
            指定 A/B 和本次题目，把分析指令交给外部
            Agent。报告保存后，改善、退步和开发方向都会关联到具体证据。
          </p>
          <p className={styles.muted}>
            没有新版记录也可以先整理基线，页面会明确标记尚未完成前后对比。
          </p>
        </div>
      )}
    </div>
  );
}
