"use client";
import { useState } from "react";
import { sampleRuns, sampleBaseline, sampleCandidate } from "../lib/fixtures";
import { summarizeRun, summarizeDimensions, compareRuns } from "../lib/domain";
import { Header, Metric, Badge, fmt } from "./report-ui";
export function ComparisonPreview() {
  const [baseId, setBaseId] = useState(sampleBaseline.id),
    [candidateId, setCandidateId] = useState(sampleCandidate.id);
  const base = sampleRuns.find((r) => r.id === baseId)!,
    candidate = sampleRuns.find((r) => r.id === candidateId)!;
  const same = baseId === candidateId,
    comparison = same ? null : compareRuns(base, candidate),
    bs = summarizeRun(base),
    cs = summarizeRun(candidate);
  const baseDimensions = summarizeDimensions(base);
  const candidateDimensions = summarizeDimensions(candidate);
  return (
    <>
      <Header
        title="对比"
        desc="按案例匹配两个示例运行，检查结果变化与证据。"
      />
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>选择运行</h2>
            <p>仅展示固定示例；比较结果由匹配案例计算。</p>
          </div>
        </div>
        <div className="pad form-grid">
          <div className="field">
            <label htmlFor="baseline">基线运行</label>
            <select
              id="baseline"
              className="input"
              value={baseId}
              onChange={(e) => setBaseId(e.target.value)}
            >
              {sampleRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.agent_version}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="candidate">候选运行</label>
            <select
              id="candidate"
              className="input"
              value={candidateId}
              onChange={(e) => setCandidateId(e.target.value)}
            >
              {sampleRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.agent_version}
                </option>
              ))}
            </select>
          </div>
          {same && (
            <div className="error full">请选择两个不同的运行进行比较。</div>
          )}
        </div>
      </div>
      {comparison && (
        <>
          <div className="section-gap metrics">
            <Metric
              label="基线运行 已评分用例通过率"
              value={bs.pass_rate == null ? "—" : fmt(bs.pass_rate * 100, "%")}
              note={"已评分 " + bs.scored + "/" + bs.selected}
            />
            <Metric
              label="候选运行 已评分用例通过率"
              value={cs.pass_rate == null ? "—" : fmt(cs.pass_rate * 100, "%")}
              note={"已评分 " + cs.scored + "/" + cs.selected}
            />
            <Metric label="退化案例" value={comparison.regressions} />
            <Metric label="修复案例" value={comparison.fixes} />
          </div>
          {!comparison.comparable && (
            <div className="notice">
              {comparison.reason || "这两个运行无法直接比较。"}
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <div>
                <h2>维度与执行指标</h2>
                <p>
                  数据集 v{base.dataset_version} / v{candidate.dataset_version}{" "}
                  · 评分标准 v{base.rubric_version} / v
                  {candidate.rubric_version}
                  ；均值仅覆盖有评分的样本。
                </p>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>基线运行</th>
                    <th>候选运行</th>
                  </tr>
                </thead>
                <tbody>
                  {baseDimensions.map((d) => {
                    const other = candidateDimensions.find(
                      (x) => x.id === d.id,
                    );
                    return (
                      <tr key={d.id}>
                        <td>{d.name} · 已评分均值</td>
                        <td className="nums">
                          {fmt(d.mean)}{" "}
                          <span className="small muted">
                            （{d.scored}/{d.selected}）
                          </span>
                        </td>
                        <td className="nums">
                          {fmt(other?.mean ?? null)}{" "}
                          <span className="small muted">
                            （{other?.scored ?? 0}/{cs.selected}）
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td>平均执行耗时</td>
                    <td>
                      {fmt(bs.average_latency_ms, " 毫秒")}{" "}
                      <span className="small muted">
                        （{bs.latency_coverage}/{bs.selected}）
                      </span>
                    </td>
                    <td>
                      {fmt(cs.average_latency_ms, " 毫秒")}{" "}
                      <span className="small muted">
                        （{cs.latency_coverage}/{cs.selected}）
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td>总费用</td>
                    <td>
                      {fmt(bs.total_cost)}{" "}
                      <span className="small muted">
                        已记录 {bs.cost_coverage}/{bs.selected}
                      </span>
                    </td>
                    <td>
                      {fmt(cs.total_cost)}{" "}
                      <span className="small muted">
                        已记录 {cs.cost_coverage}/{cs.selected}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="pad small muted">
              这是有限样本的描述性对比，不表示统计显著性；待评与执行错误单列，不当作分数回归。
            </p>
          </div>
          <div className="panel section-gap">
            <div className="panel-head">
              <div>
                <h2>案例变化</h2>
                <p>通过案例内容与标识匹配；点击运行结果查看对应证据。</p>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>案例</th>
                    <th>基线运行</th>
                    <th>候选运行</th>
                    <th>变化</th>
                    <th>证据</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.rows.map((row) => (
                    <tr key={row.case_id}>
                      <td>
                        {row.title}
                        <div className="mono muted">{row.case_id}</div>
                      </td>
                      <td>
                        {row.baseline ? (
                          <Badge value={row.baseline.verdict} />
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {row.candidate ? (
                          <Badge value={row.candidate.verdict} />
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <Badge value={row.change} />
                      </td>
                      <td>
                        <div className="row">
                          {row.baseline && (
                            <a
                              className="click small"
                              href={
                                "/evaluations/" +
                                base.id +
                                "?mode=example&case=" +
                                encodeURIComponent(row.case_id)
                              }
                            >
                              基线运行
                            </a>
                          )}
                          {row.candidate && (
                            <a
                              className="click small"
                              href={
                                "/evaluations/" +
                                candidate.id +
                                "?mode=example&case=" +
                                encodeURIComponent(row.case_id)
                              }
                            >
                              候选运行
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}
