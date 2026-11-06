"use client";
import { useState } from "react";
import { sampleDataset, sampleRubric } from "../lib/fixtures";
import { validateJsonl } from "../lib/domain";
import { Header, Tabs } from "./report-ui";
import { Input } from "./ui/input";
export function DatasetPreview() {
  const [tab, setTab] = useState("数据集"),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState("全部"),
    [text, setText] = useState(""),
    [fileName, setFileName] = useState(""),
    [fileError, setFileError] = useState("");
  const categories = Array.from(
    new Set(sampleDataset.cases.flatMap((c) => c.categories)),
  );
  const cases = sampleDataset.cases.filter(
    (c) =>
      (category === "全部" || c.categories.includes(category)) &&
      JSON.stringify(c).toLowerCase().includes(query.toLowerCase()),
  );
  const validation = fileName && !fileError ? validateJsonl(text) : null;
  const download = () => {
    const blob = new Blob(
      [
        sampleDataset.cases
          .map((c) =>
            JSON.stringify({
              schema_version: 1,
              case_id: c.case_id,
              input: c.input,
              expected: c.expected,
              categories: c.categories,
              metadata: { title: c.title },
            }),
          )
          .join("\n") + "\n",
      ],
      { type: "application/x-ndjson" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "example-dataset.jsonl";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <Header
        title="数据集"
        desc="查看示例数据集、评分维度与本地文件预览。"
        action={
          <button className="button" onClick={download}>
            下载示例 JSONL
          </button>
        }
      />
      <div className="panel">
        <Tabs
          labels={["数据集", "评分标准", "本地 JSONL 预览"]}
          active={tab}
          set={setTab}
        />
        {tab === "数据集" ? (
          <>
            <div className="panel-head">
              <div>
                <h2>
                  {sampleDataset.name}{" "}
                  <span className="badge info">v{sampleDataset.version}</span>
                </h2>
                <p>
                  {sampleDataset.description} · {sampleDataset.cases.length}{" "}
                  条案例
                </p>
              </div>
            </div>
            <div className="toolbar">
              <input
                className="input"
                aria-label="搜索案例"
                placeholder="搜索案例"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <select
                className="input"
                aria-label="案例分类"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option>全部</option>
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
              <span className="small muted">
                显示 {cases.length} / {sampleDataset.cases.length}
              </span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>案例编号</th>
                    <th>名称</th>
                    <th>分类</th>
                    <th>内容哈希</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.case_id}>
                      <td className="mono">{c.case_id}</td>
                      <td>{c.title}</td>
                      <td>{c.categories.join("、")}</td>
                      <td className="mono muted">{c.content_hash}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : tab === "评分标准" ? (
          <>
            <div className="panel-head">
              <div>
                <h2>
                  {sampleRubric.name}{" "}
                  <span className="badge info">v{sampleRubric.version}</span>
                </h2>
                <p>示例评分标准 · {sampleRubric.dimensions.length} 个维度</p>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>维度</th>
                    <th>方法</th>
                    <th>权重</th>
                    <th>必要证据</th>
                    <th>硬性失败</th>
                  </tr>
                </thead>
                <tbody>
                  {sampleRubric.dimensions.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <strong>{d.name}</strong>
                        <div className="small muted">{d.description}</div>
                      </td>
                      <td>
                        {
                          {
                            code: "代码评分",
                            llm: "模型评分",
                            human: "人工复核",
                          }[d.method]
                        }
                      </td>
                      <td>{d.weight ?? "—"}</td>
                      <td>
                        {d.required_evidence
                          .map(
                            (e) =>
                              (
                                ({
                                  final_output: "最终输出",
                                  tool_call: "工具调用",
                                  tool_result: "工具返回",
                                }) as Record<string, string>
                              )[e] || e,
                          )
                          .join("、") || "—"}
                      </td>
                      <td>{d.hard_failure ? "是" : "否"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="pad stack">
            <div className="notice">
              仅在当前页面读取和校验文件，不会保存或导入数据集。文件上限为 5
              MiB。
            </div>
            <div className="field">
              <label htmlFor="jsonl-file">选择 JSONL 文件</label>
              <input
                id="jsonl-file"
                type="file"
                accept=".jsonl,.ndjson,text/plain"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  setFileName(f?.name || "");
                  setText("");
                  setFileError("");
                  if (!f) return;
                  if (f.size > 5 * 1024 * 1024) {
                    setFileError("预览文件不能超过 5 MiB，请选择较小文件。");
                    return;
                  }
                  try {
                    setText(await f.text());
                  } catch {
                    setFileError("无法读取文件，请重新选择。");
                  }
                }}
              />
            </div>
            {fileName && <p>{fileName}</p>}
            {fileError && (
              <div className="error" role="alert">
                {fileError}
              </div>
            )}
            {validation &&
              (validation.valid ? (
                <div className="notice">
                  校验通过 · {validation.cases.length} 条案例 · 分类：
                  {validation.categories.join("、") || "无"}
                </div>
              ) : (
                <div className="error">
                  校验未通过
                  {validation.errors.map((e, i) => (
                    <div key={i}>
                      {e.line > 0 ? "第 " + e.line + " 行：" : ""}
                      {e.message}
                    </div>
                  ))}
                </div>
              ))}
            {text && <pre className="code">{text}</pre>}
          </div>
        )}
      </div>
    </>
  );
}
