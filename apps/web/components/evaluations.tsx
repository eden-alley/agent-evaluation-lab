"use client";
import { useState } from "react";
import { sampleDataset, sampleRuns } from "../lib/fixtures";
import { summarizeRun } from "../lib/domain";
import { Header } from "./report-ui";
export function EvaluationPreview() {
  const [count, setCount] = useState(8);
  return (
    <>
      <Header title="评测" desc="浏览示例运行、执行状态和评分证据。" />
      <div className="notice" style={{ marginBottom: 20 }}>
        运行执行器尚未接入。下面的运行是固定示例；选择数量仅用于预览，不能启动执行。
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>示例运行</h2>
            <p>固定的演示结果，不会写入工作区。</p>
          </div>
          <div className="row">
            <label htmlFor="selected-count" className="small muted">
              预览选择数量
            </label>
            <input
              id="selected-count"
              className="input"
              type="number"
              min="1"
              max={sampleDataset.cases.length}
              value={count}
              onChange={(e) =>
                setCount(
                  Math.max(
                    1,
                    Math.min(
                      sampleDataset.cases.length,
                      Number(e.target.value) || 1,
                    ),
                  ),
                )
              }
              style={{ width: 72 }}
            />
          </div>
        </div>
        <div className="pad small muted">
          预览选择 {count} / {sampleDataset.cases.length} 条案例：
          {sampleDataset.cases
            .slice(0, count)
            .map((c) => c.case_id)
            .join("、")}
          。现有示例运行结果不会因此改变。
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>运行</th>
                <th>智能体版本</th>
                <th>数据集 / 评分标准</th>
                <th>执行</th>
                <th>评分</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sampleRuns.map((run) => {
                const s = summarizeRun(run);
                return (
                  <tr key={run.id}>
                    <td>
                      <strong>{run.name}</strong>
                      <div className="mono muted">{run.id}</div>
                    </td>
                    <td>
                      {run.agent_name}{" "}
                      <span className="mono">{run.agent_version}</span>
                    </td>
                    <td>
                      v{run.dataset_version} / v{run.rubric_version}
                    </td>
                    <td>
                      {s.finished}/{s.selected}
                    </td>
                    <td>
                      {s.scored}/{s.selected}
                    </td>
                    <td>
                      <a
                        className="button small"
                        href={"/evaluations/" + run.id + "?mode=example"}
                      >
                        查看详情
                      </a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
