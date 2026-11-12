"use client";

import { useEffect, useState } from "react";
import { request } from "../lib/api";
import { artifactUrl } from "../lib/imported-runs";

type Group = {
  line: number;
  phase: number;
  heading: string;
  text: string;
  event_ids: number[];
  evidence: { line: number; label: string; text: string }[];
};

type Trace = { source: string | null; groups: Group[] };

const replayHighlights: Record<string, { text: string; events: number[] }[]> = {
  U01: [
    {
      text: "第 17 次请求后，模型改了 Click 生成帮助信息的代码。第 25 次，它运行了 8 项测试，全部通过。",
      events: [66, 90],
    },
    {
      text: "第 26 到 30 次，它继续检查改动和源码。到观测点时，源码和测试都已就位，交付报告还没写。",
      events: [93, 105],
    },
    {
      text: "第 31 次，模型写出交付报告。第 32 次重跑测试，8 项全过。随后它在第 33 次提交最终答复。",
      events: [108, 111, 114],
    },
  ],
  U03: [
    {
      text: "到第 30 次，模型主要在读代码，并把两段源码复制到临时文件。业务源码仍与初始版本一致。",
      events: [98, 101],
    },
    {
      text: "第 48 次，它跑了公开测试，结果仍显示旧任务卡在等待输入。随后又回到读取和切片，直到第 60 次停止。",
      events: [159, 197, 198],
    },
  ],
  U05: [
    {
      text: "第 15 次，模型修改了终端程序。第 19 次，它把新测试加进了题目要求保持原样的已有测试文件。",
      events: [58, 70],
    },
    {
      text: "第 24 次写出报告，第 26 次跑通 7 项自测，第 27 次提交答复。独立功能验收通过，改动范围未满足题目要求。",
      events: [85, 91, 94],
    },
  ],
  C01: [
    {
      text: "第 30 次时，模型还在查看源码，工作区只有一个临时行号文件，没有定位报告。",
      events: [20, 95],
    },
    {
      text: "接下来 30 次请求仍在运行命令查看源码。到第 60 次停止时，定位报告仍未写出。",
      events: [185, 186],
    },
  ],
};

export function TraceNarrative({
  runId,
  caseId,
}: {
  runId: string;
  caseId: string;
}) {
  const [trace, setTrace] = useState<Trace>();
  const [error, setError] = useState("");
  const [selectedLine, setSelectedLine] = useState<number>();
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    let active = true;
    request<Trace>(
      `/evaluation-runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/trace`,
    )
      .then((value) => {
        if (active) setTrace(value);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error ? failure.message : "轨迹读取失败。",
          );
      });
    return () => {
      active = false;
    };
  }, [runId, caseId]);
  const highlights =
    runId === "harness-step30-bailian-20261110"
      ? replayHighlights[caseId]
      : undefined;
  const groups = trace?.groups ?? [];

  function reveal(line: number) {
    setShowAll(true);
    setSelectedLine(line);
  }

  useEffect(() => {
    if (selectedLine !== undefined) {
      document
        .getElementById(`trace-step-${selectedLine}`)
        ?.scrollIntoView({ block: "start" });
    }
  }, [selectedLine]);

  return (
    <div className="panel pad">
      <div className="row between">
        <h2>执行过程</h2>
        {trace?.source && (
          <a
            className="button small"
            href={artifactUrl(runId, trace.source, true)}
          >
            下载完整原始轨迹
          </a>
        )}
      </div>
      {error ? (
        <p role="alert">{error}</p>
      ) : !trace ? (
        <p role="status">正在读取执行过程…</p>
      ) : groups.length === 0 ? (
        <p className="muted">这次导入没有可展开的事件记录。</p>
      ) : (
        <>
          {highlights && (
            <>
              {highlights.map((highlight) => (
                <div className="grade" key={highlight.events[0]}>
                  <p>{highlight.text}</p>
                  <div className="row">
                    {highlight.events.map((event) => {
                      const group = groups.find((entry) =>
                        entry.event_ids.includes(event),
                      );
                      return (
                        group && (
                          <button
                            key={event}
                            className="button small"
                            onClick={() => reveal(group.line)}
                          >
                            查看事件 {event}
                          </button>
                        )
                      );
                    })}
                  </div>
                </div>
              ))}
              <button
                className="button small"
                onClick={() => setShowAll(!showAll)}
              >
                {showAll ? "收起逐步记录" : "展开逐步记录"}
              </button>
            </>
          )}
          {(!highlights || showAll) &&
            groups.map((group) => (
              <section
                id={`trace-step-${group.line}`}
                className="grade"
                key={group.line}
              >
                <h3>{group.heading}</h3>
                <p>{group.text}</p>
                {group.evidence.length > 0 && (
                  <details
                    open={selectedLine === group.line ? true : undefined}
                  >
                    <summary>展开原始操作与结果</summary>
                    {group.evidence.map((entry) => (
                      <div key={entry.line}>
                        <p className="small muted">{entry.label}</p>
                        <pre
                          className="code"
                          style={{ maxHeight: 320, overflow: "auto" }}
                        >
                          {entry.text}
                        </pre>
                      </div>
                    ))}
                  </details>
                )}
              </section>
            ))}
        </>
      )}
    </div>
  );
}
