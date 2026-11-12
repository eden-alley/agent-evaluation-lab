"use client";
import { useEffect, useState } from "react";
import {
  FolderKanban,
  Database,
  FlaskConical,
  GitCompareArrows,
  Settings,
  Layers3,
  BookOpen,
} from "lucide-react";
import { Projects } from "./projects";
import {
  DatasetPreview,
  EvaluationPreview,
  RunPreview,
  ComparisonPreview,
} from "./previews";
import { api } from "../lib/api";
import type { Health } from "../lib/types";
import { Button } from "./ui/button";
import { Skills } from "./skills";
import { Connections } from "./connections";
import { DatasetWorkspace } from "./dataset-workspace";
import { ImportedRuns } from "./imported-runs";
import { ComparisonWorkspace } from "./comparison-workspace";

const nav = [
  ["projects", "项目", FolderKanban],
  ["skills", "内置技能", BookOpen],
  ["datasets", "数据集", Database],
  ["evaluations", "评测", FlaskConical],
  ["comparison", "对比", GitCompareArrows],
  ["settings", "设置", Settings],
] as const;
export function Lab({ page, id }: { page: string; id?: string }) {
  const [example, setExample] = useState(false);
  const [modeReady, setModeReady] = useState(false);
  useEffect(() => {
    setExample(
      new URLSearchParams(window.location.search).get("mode") === "example",
    );
    setModeReady(true);
  }, []);
  const current = page === "run" ? "evaluations" : page;
  const link = (path: string) => path + (example ? "?mode=example" : "");
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Layers3 size={18} />
          </div>
          <span>
            智能体评测台<small>本地工作区</small>
          </span>
        </div>
        <nav className="nav" aria-label="主导航">
          {nav.map(([key, label, Icon]) => (
            <a
              key={key}
              href={link("/" + key)}
              className={current === key ? "active" : ""}
            >
              <Icon size={17} />
              {label}
            </a>
          ))}
        </nav>
        <div className="side-bottom small muted">
          智能体评测台
          <br />
          v0.1 · 框架预览
        </div>
      </aside>
      <main className="main">
        <div className="context">
          <span>
            工作区 <span className="muted"> / </span>{" "}
            <strong>{nav.find((n) => n[0] === current)?.[1]}</strong>
          </span>
          <span>
            {example ? "示例预览" : "本地工作区"} ·{" "}
            <a
              className="click"
              href={
                example
                  ? "/" + current
                  : current === "projects" ||
                      current === "settings" ||
                      current === "skills"
                    ? "/evaluations/example-candidate?mode=example"
                    : "/" + current + "?mode=example"
              }
            >
              {example ? "切换到工作区" : "切换到示例"}
            </a>
          </span>
        </div>
        <div className="content">
          {example && (
            <div className="preview">
              <span>
                <strong>示例预览模式</strong> ·
                评测数据为演示样本，不代表真实执行结果。项目、内置技能和设置页面
                仍显示真实工作区信息。
              </span>
              <a href={"/" + current}>返回真实工作区</a>
            </div>
          )}
          {!modeReady ? (
            <p className="muted" role="status">
              正在打开工作区…
            </p>
          ) : page === "projects" ? (
            <Projects />
          ) : page === "settings" ? (
            <SettingsPage />
          ) : page === "skills" ? (
            <Skills />
          ) : page === "datasets" && !example ? (
            <DatasetWorkspace />
          ) : !example && (page === "evaluations" || page === "run") ? (
            <ImportedRuns id={page === "run" ? id : undefined} />
          ) : page === "comparison" && !example ? (
            <ComparisonWorkspace />
          ) : !example ? (
            <EmptyPage page={page} />
          ) : page === "datasets" ? (
            <DatasetPreview />
          ) : page === "evaluations" ? (
            <EvaluationPreview />
          ) : page === "comparison" ? (
            <ComparisonPreview />
          ) : (
            <RunPreview id={id || ""} />
          )}
        </div>
      </main>
    </div>
  );
}
function EmptyPage({ page }: { page: string }) {
  const values: Record<string, [string, string, string]> = {
    datasets: [
      "数据集",
      "数据集尚未接入",
      "数据集存储与版本管理将在后续接入。可以先查看示例数据与评分标准。",
    ],
    evaluations: [
      "评测",
      "暂无评测运行",
      "执行器尚未接入，当前没有真实评测结果。可以先查看示例运行和证据。",
    ],
    comparison: [
      "对比",
      "暂无可比较的运行",
      "评测执行与结果存储尚未接入。可以先查看示例对比。",
    ],
    run: ["评测", "暂无真实运行", "执行器尚未接入。可以先查看示例运行。"],
  };
  const [title, heading, desc] = values[page] || values.run;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p>
            查看和管理评估工作中的
            {page === "datasets"
              ? "数据与评分标准"
              : page === "comparison"
                ? "变化"
                : "运行与证据"}
            。
          </p>
        </div>
      </div>
      <div className="panel empty">
        <Database className="empty-icon" size={30} />
        <h2>{heading}</h2>
        <p>{desc}</p>
        <Button asChild variant="primary">
          <a
            href={
              page === "run" || page === "evaluations"
                ? "/evaluations/example-candidate?mode=example"
                : "/" + page + "?mode=example"
            }
          >
            查看示例
          </a>
        </Button>
      </div>
    </>
  );
}
function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setHealth(await api.health());
    } catch (e) {
      setError(e instanceof Error ? e.message : "连接失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>设置</h1>
          <p>连接外部 Coding Agent，查看本地服务与工作区能力。</p>
        </div>
        <button className="button" onClick={load}>
          重新检查
        </button>
      </div>
      <Connections />
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>服务状态</h2>
            <p>检查本地服务接口的可用性</p>
          </div>
          {health && <span className="badge good">● 正常</span>}
        </div>
        <div className="pad stack">
          {loading ? (
            <p className="muted">正在检查…</p>
          ) : error ? (
            <div className="error">
              {error}{" "}
              <button className="button small" onClick={load}>
                重试
              </button>
            </div>
          ) : (
            health && (
              <>
                <div className="row between">
                  <span>数据库</span>
                  <span className="mono">
                    {health.database} · {health.journal_mode.toUpperCase()}
                  </span>
                </div>
                <div className="row between">
                  <span>项目与智能体配置</span>
                  <span
                    className={
                      "badge " +
                      (health.capabilities.projects &&
                      health.capabilities.agent_registration &&
                      health.capabilities.agent_check
                        ? "good"
                        : "warn")
                    }
                  >
                    {health.capabilities.projects &&
                    health.capabilities.agent_registration &&
                    health.capabilities.agent_check
                      ? "已支持"
                      : "部分不可用"}
                  </span>
                </div>
                <div className="row between">
                  <span>内置技能与质量报告交接</span>
                  <span
                    className={
                      "badge " +
                      (health.capabilities.dataset_quality_handoff &&
                      health.capabilities.skill_catalog
                        ? "good"
                        : "warn")
                    }
                  >
                    {health.capabilities.dataset_quality_handoff &&
                    health.capabilities.skill_catalog
                      ? "已支持"
                      : "尚未接入"}
                  </span>
                </div>
                <div className="row between">
                  <span>评测执行</span>
                  <span
                    className={
                      "badge " +
                      (health.capabilities.evaluation_execution
                        ? "good"
                        : "warn")
                    }
                  >
                    {health.capabilities.evaluation_execution
                      ? "已支持"
                      : "尚未接入"}
                  </span>
                </div>
              </>
            )
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>界面</h2>
            <p>设计来源与工作范围</p>
          </div>
        </div>
        <div className="pad stack">
          <div className="row between">
            <span>主题</span>
            <span>智能体演进设计规范 v0.1</span>
          </div>
          <p className="small muted">
            支持外部工具接入、用户发布的技能、评测集草案与质量报告审阅；真实评测执行将在后续接入。
          </p>
        </div>
      </div>
    </>
  );
}
