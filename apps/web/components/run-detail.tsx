"use client";
import { useState, useRef, useEffect } from "react";
import { sampleRuns } from "../lib/fixtures";
import type { EvaluationRun, Trial } from "../lib/types";
import {
  Header,
  RunMetrics,
  Badge,
  Tabs,
  fmt,
  json,
  status,
} from "./report-ui";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
export function RunPreview({ id }: { id: string }) {
  const run = sampleRuns.find((r) => r.id === id);
  if (!run)
    return (
      <>
        <Header title="未找到示例运行" desc="该示例不存在。" />
        <a className="button" href="/evaluations?mode=example">
          返回示例运行
        </a>
      </>
    );
  return <RunDetail run={run} />;
}
function RunDetail({ run }: { run: EvaluationRun }) {
  const [selected, setSelected] = useState(run.trials[0]?.id),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("全部"),
    [view, setView] = useState("案例结果");
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("case");
    const matching = run.trials.find((t) => t.case_id === initial);
    if (matching) {
      setSelected(matching.id);
      setView("执行轨迹与评分证据");
    }
  }, [run]);
  const trial = run.trials.find((t) => t.id === selected) || run.trials[0];
  function openTrial(item: Trial) {
    setSelected(item.id);
    setView("执行轨迹与评分证据");
    const url = new URL(window.location.href);
    url.searchParams.set("case", item.case_id);
    window.history.replaceState(null, "", url);
  }
  const visible = run.trials.filter(
    (t) =>
      (filter === "全部" ||
        t.verdict === filter ||
        t.execution_status === filter ||
        (filter === "error" && t.execution_status === "timeout")) &&
      JSON.stringify([t.case_id, t.title, t.category])
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="breadcrumb">
        <a href="/evaluations?mode=example">评测</a> / {run.name}
      </div>
      <Header
        title={run.name}
        desc={
          run.agent_name +
          " · " +
          run.agent_version +
          "   /   数据集 v" +
          run.dataset_version +
          "   /   评分标准 v" +
          run.rubric_version
        }
        action={
          <a href="/comparison?mode=example" className="button">
            比较运行
          </a>
        }
      />
      <RunMetrics run={run} />
      <div className="run-tabs">
        <Tabs
          labels={["案例结果", "执行轨迹与评分证据"]}
          active={view}
          set={setView}
        />
      </div>
      {view === "案例结果" ? (
        <div className="panel results-panel">
          <div className="panel-head">
            <div>
              <h2>案例结果</h2>
              <p>
                分别记录执行状态与评估结论。点击案例，进入对应的评分与证据。
              </p>
            </div>
            <span className="small muted">
              显示 {visible.length} / {run.trials.length}
            </span>
          </div>
          <div className="toolbar">
            <Input
              aria-label="搜索运行案例"
              placeholder="搜索案例编号或名称"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="input"
              aria-label="筛选状态"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option>全部</option>
              <option value="pass">通过</option>
              <option value="fail">未通过</option>
              <option value="pending_review">待复核</option>
              <option value="error">执行错误</option>
            </select>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>案例</th>
                  <th>分类</th>
                  <th>执行状态</th>
                  <th>评估结论</th>
                  <th>耗时</th>
                  <th>词元数</th>
                  <th>成本</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((t) => (
                  <tr
                    key={t.id}
                    className={t.id === trial?.id ? "selected" : ""}
                  >
                    <td>
                      <button
                        className="button link"
                        onClick={() => openTrial(t)}
                      >
                        {t.title}
                      </button>
                      <div className="mono muted">{t.case_id}</div>
                    </td>
                    <td>{t.category}</td>
                    <td>
                      <Badge value={t.execution_status} />
                    </td>
                    <td>
                      <Badge value={t.verdict} />
                    </td>
                    <td className="nums">{fmt(t.latency_ms, " 毫秒")}</td>
                    <td className="nums">{fmt(t.tokens)}</td>
                    <td className="nums">{fmt(t.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pad small muted">
            “—”表示未记录，不计作零。覆盖数见上方汇总。
          </div>
        </div>
      ) : (
        trial && (
          <>
            <div className="case-context">
              <button
                className="button small"
                onClick={() => setView("案例结果")}
              >
                返回案例列表
              </button>
              <label htmlFor="trace-case">当前案例</label>
              <select
                id="trace-case"
                className="input"
                value={trial.id}
                onChange={(event) => {
                  const item = run.trials.find(
                    (t) => t.id === event.target.value,
                  );
                  if (item) openTrial(item);
                }}
              >
                {run.trials.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.case_id} · {t.title}
                  </option>
                ))}
              </select>
              <Badge value={trial.verdict} />
            </div>
            <Evidence key={trial.id} trial={trial} />
          </>
        )
      )}
    </>
  );
}
function Evidence({ trial }: { trial: Trial }) {
  const [spanId, setSpanId] = useState(trial.spans[0]?.id),
    [tab, setTab] = useState("输入");
  const span = trial.spans.find((s) => s.id === spanId) || trial.spans[0];
  const detailRef = useRef<HTMLDivElement>(null);
  function showEvidence(id: string) {
    if (!trial.spans.some((s) => s.id === id)) return;
    setSpanId(id);
    setTab("输出");
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    detailRef.current?.focus();
  }
  return (
    <div className="section-gap">
      <div className="page-head">
        <div>
          <h2>证据详情 · {trial.title}</h2>
          <p>
            轨迹编号 <span className="mono">{trial.trace_id}</span> ·
            选择节点查看输入、输出与错误。
          </p>
        </div>
      </div>
      <div className="split">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>执行轨迹</h2>
              <p>{trial.spans.length} 个节点</p>
            </div>
          </div>
          <div className="evidence">
            <div className="tree">
              {trial.spans.map((s) => (
                <button
                  key={s.id}
                  className={span?.id === s.id ? "selected" : ""}
                  onClick={() => setSpanId(s.id)}
                  style={{ paddingLeft: s.parent_id ? 20 : 9 }}
                >
                  <span className="small muted">
                    {
                      { agent: "智能体", llm: "模型调用", tool: "工具调用" }[
                        s.type
                      ]
                    }
                  </span>
                  <br />
                  {s.name} · {status(s.status)}
                </button>
              ))}
            </div>
            <div className="detail" ref={detailRef} tabIndex={-1}>
              {span ? (
                <>
                  <div className="pad">
                    <strong>{span.name}</strong>
                    <p className="small muted" style={{ marginTop: 6 }}>
                      {
                        { agent: "智能体", llm: "模型调用", tool: "工具调用" }[
                          span.type
                        ]
                      }{" "}
                      · {fmt(span.duration_ms, " 毫秒")} · {span.started_at}
                    </p>
                  </div>
                  <Tabs
                    labels={["输入", "输出", "错误"]}
                    active={tab}
                    set={setTab}
                  />
                  <div className="pad">
                    <pre className="code">
                      {json(
                        tab === "输入"
                          ? span.input
                          : tab === "输出"
                            ? span.output
                            : span.error,
                      )}
                    </pre>
                  </div>
                </>
              ) : (
                <div className="pad muted">暂无轨迹节点。</div>
              )}
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>评分维度</h2>
              <p>点击证据来源可定位左侧轨迹节点。</p>
            </div>
            <Badge value={trial.verdict} />
          </div>
          <div className="pad">
            {trial.grades.length ? (
              trial.grades.map((g) => (
                <div className="grade" key={g.dimension_id}>
                  <div className="row between">
                    <strong>{g.name}</strong>
                    <span>
                      <Badge value={g.status} />　
                      <strong>{g.score == null ? "—" : g.score}</strong>
                    </span>
                  </div>
                  <p>{g.reason}</p>
                  <div className="row small">
                    {g.evidence_span_ids.length ? (
                      g.evidence_span_ids.map((id) => (
                        <Button
                          type="button"
                          variant="link"
                          size="small"
                          key={id}
                          disabled={!trial.spans.some((s) => s.id === id)}
                          onClick={() => showEvidence(id)}
                        >
                          证据来源：{id}
                        </Button>
                      ))
                    ) : (
                      <span className="muted">无关联证据</span>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">暂无评分维度。</p>
            )}
            {trial.error && (
              <div className="error" style={{ marginTop: 12 }}>
                执行错误：{trial.error}
              </div>
            )}
            {trial.output && (
              <div className="grade">
                <strong>最终输出</strong>
                <pre className="code">{trial.output}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
