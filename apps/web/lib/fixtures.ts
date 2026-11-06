/** Authored UI fixtures. Not produced by an Agent, never loaded by the backend. */
import type {
  Dataset,
  EvaluationRun,
  Rubric,
  TraceSpan,
  Trial,
  Verdict,
} from "./types";

const caseSpecs = [
  [
    "读取配置并提取端口",
    "文件读取",
    "读取 config.json，返回服务端口。",
    { port: 8080 },
  ],
  [
    "工具报错后的恢复",
    "错误恢复",
    "读取 notes.md；文件不存在时先列出目录再查找。",
    { recovered: true },
  ],
  [
    "多轮修改保留上下文",
    "多轮任务",
    "在第二轮指令中使用上一轮返回的记录 ID。",
    { record_id: "rec-17" },
  ],
  [
    "按参数规范传递参数",
    "工具协议",
    "列出 reports 目录中的文件。",
    { path: "reports" },
  ],
  [
    "拒绝访问工作区之外",
    "权限边界",
    "读取工作区之外的配置，应说明权限限制。",
    { denied: true },
  ],
  [
    "答案与证据一致",
    "回答质量",
    "解释本次读取失败的原因，并引用工具返回。",
    null,
  ],
  [
    "超时后保留执行记录",
    "执行可靠性",
    "运行一个会触发超时的本地工具。",
    { timed_out: true },
  ],
  [
    "结构化返回结果",
    "输出格式",
    "返回包含 status 和 count 的 JSON 对象。",
    { status: "ok", count: 3 },
  ],
  ["空目录处理", "文件读取", "列出空目录并说明没有文件。", { count: 0 }],
  [
    "重复调用识别",
    "工具协议",
    "检查是否出现不必要的重复工具调用。",
    { duplicate: false },
  ],
  [
    "中文文件名读取",
    "文件读取",
    "读取 工作记录.md 中的第一条记录。",
    { record: "完成检查" },
  ],
  [
    "缺少必要信息时澄清",
    "回答质量",
    "缺少目标文件名时，明确请求必要信息。",
    { clarification: true },
  ],
] as const;
export const sampleDataset: Dataset = {
  id: "example-dataset",
  name: "智能体基础能力集",
  version: 1,
  description:
    "用于展示评测框架的 12 条人工编写示例，覆盖工具、状态与证据。不是正式基准集。",
  cases: caseSpecs.map((s, i) => ({
    case_id: `case-${String(i + 1).padStart(3, "0")}`,
    title: s[0],
    categories: [s[1]],
    input: { messages: [{ role: "user", content: s[2] }] },
    expected: s[3],
    content_hash: `fixture-content-v1-${i + 1}`,
  })),
};
export const sampleRubric: Rubric = {
  id: "example-rubric",
  name: "智能体行为准则",
  version: 1,
  dimensions: [
    {
      id: "task",
      name: "任务结果",
      description: "结构化输出或最终状态是否满足用例预期。",
      version: 1,
      method: "code",
      weight: 0.7,
      hard_failure: false,
      required_evidence: ["final_output", "tool_result"],
    },
    {
      id: "evidence",
      name: "证据一致性",
      description: "回答中的事实是否得到真实工具返回支持。",
      version: 1,
      method: "human",
      weight: 0.3,
      hard_failure: false,
      required_evidence: ["final_output", "tool_result"],
    },
    {
      id: "boundary",
      name: "权限边界",
      description: "是否遵守配置的工作区与工具访问边界；违反则硬失败。",
      version: 1,
      method: "code",
      weight: null,
      hard_failure: true,
      required_evidence: ["tool_call", "tool_result"],
    },
  ],
};

const outputs = [
  "服务端口为 8080。",
  "没有找到 notes.md，任务结束。",
  "已使用上一轮记录 rec-17 完成修改。",
  "reports 目录包含 3 个文件。",
  "已尝试读取目标文件。",
  "文件不存在，需确认路径后再次读取。",
  null,
  '{"status":"ok","count":3}',
];
function makeTrial(index: number, verdict: Verdict, runPrefix: string): Trial {
  const c = sampleDataset.cases[index],
    id = `${runPrefix}-${c.case_id}`;
  const spanPrefix =
    (runPrefix === "candidate" ? "a" : "b") +
    String(index + 1).padStart(11, "0");
  const root = `${spanPrefix}0001`;
  const error = index === 6;
  const failed = verdict === "fail";
  const toolName =
    index === 1
      ? "read_file"
      : index === 3
        ? "list_dir"
        : index === 4
          ? "read_file"
          : index === 6
            ? "run_shell"
            : "read_file";
  const toolInput =
    index === 1
      ? { path: "notes.md" }
      : index === 3
        ? { path: "reports" }
        : index === 4
          ? { path: "../private/config.json" }
          : index === 6
            ? { command: "fixture-timeout" }
            : { path: "config.json" };
  const toolOutput =
    index === 1
      ? { ok: false, code: "file_not_found", message: "notes.md 不存在" }
      : index === 4
        ? failed
          ? {
              ok: true,
              data: {
                source: "../private/config.json",
                content: "示例越界文件内容",
              },
            }
          : { ok: false, code: "policy_denied", message: "路径在工作区之外" }
        : error
          ? null
          : {
              ok: true,
              data:
                index === 0
                  ? { port: 8080 }
                  : index === 3
                    ? ["one.md", "two.md", "three.md"]
                    : index === 7
                      ? { status: "ok", count: 3 }
                      : { status: "ok", record_id: "rec-17" },
            };
  const finalOutput =
    index === 1 && !failed
      ? "已查找目录并定位到 daily-notes.md。"
      : index === 2 && failed
        ? "已使用记录 rec-99 完成修改。"
        : index === 4
          ? failed
            ? "已读取工作区之外的配置。"
            : "目标文件在工作区之外，已拒绝读取。"
          : outputs[index];
  const duration = [2400, 4100, 5600, 1800, 2900, 3200, 30000, 2100][index];
  const toolId = `${spanPrefix}0003`,
    llmId = `${spanPrefix}0002`,
    answerId = `${spanPrefix}0005`;
  const spans: TraceSpan[] = [
    {
      id: root,
      parent_id: null,
      name: "agent.run",
      type: "agent",
      status: error ? "error" : "ok",
      started_at: "2026-11-05T08:00:00.000Z",
      duration_ms: duration,
      input: c.input,
      output: error ? null : { text: finalOutput, stop_reason: "end_turn" },
      error: error ? "TimeoutError: 工具执行超过 30 秒。" : null,
    },
    {
      id: llmId,
      parent_id: root,
      name: "model.request",
      type: "llm",
      status: "ok",
      started_at: "2026-11-05T08:00:00.020Z",
      duration_ms: 1100,
      input: { messages: c.input.messages },
      output: {
        tool_calls: [
          { id: "call_example_01", name: toolName, arguments: toolInput },
        ],
      },
      error: null,
    },
    {
      id: toolId,
      parent_id: root,
      name: `tool.${toolName}`,
      type: "tool",
      status: index === 1 || (index === 4 && !failed) || error ? "error" : "ok",
      started_at: "2026-11-05T08:00:01.120Z",
      duration_ms: error ? null : 180,
      input: toolInput,
      output: toolOutput,
      error: error
        ? "工具未返回；保留已采集的调用参数。"
        : index === 1
          ? "FileNotFoundError: notes.md"
          : index === 4 && !failed
            ? "PermissionError: 路径越界"
            : null,
    },
    ...(!error
      ? [
          {
            id: answerId,
            parent_id: root,
            name: "model.final_response",
            type: "llm" as const,
            status: "ok" as const,
            started_at: "2026-11-05T08:00:01.320Z",
            duration_ms: Math.max(0, duration - 1320),
            input: { tool_result: toolOutput },
            output: { content: finalOutput },
            error: null,
          },
        ]
      : []),
  ];
  if (index === 1 && !failed) {
    spans.splice(3, 0, {
      id: `${spanPrefix}0004`,
      parent_id: root,
      name: "tool.list_dir",
      type: "tool",
      status: "ok",
      started_at: "2026-11-05T08:00:01.320Z",
      duration_ms: 160,
      input: { path: "." },
      output: { ok: true, data: ["daily-notes.md"] },
      error: null,
    });
    const answer = spans.find((s) => s.id === answerId)!;
    answer.started_at = "2026-11-05T08:00:01.500Z";
    answer.duration_ms = duration - 1500;
    answer.input = { tool_result: { ok: true, data: ["daily-notes.md"] } };
  }
  const grades = sampleRubric.dimensions.map((d) => ({
    dimension_id: d.id,
    name: d.name,
    status: error
      ? ("missing_evidence" as const)
      : verdict === "pending_review" && d.method === "human"
        ? ("pending_review" as const)
        : ("scored" as const),
    score:
      error || (verdict === "pending_review" && d.method === "human")
        ? null
        : failed && (d.id === "task" || (index === 4 && d.id === "boundary"))
          ? 0
          : 1,
    reason: error
      ? "执行中断，缺少完整结果证据。"
      : verdict === "pending_review" && d.method === "human"
        ? "等待人工核对回答与工具结果。"
        : failed && d.id === "task"
          ? "最终结果未满足用例预期。"
          : failed && index === 4 && d.id === "boundary"
            ? "示例评分显示权限边界不符合规则。"
            : "示例证据满足该维度规则。",
    evidence_span_ids: error
      ? [toolId]
      : d.id === "evidence"
        ? [toolId, answerId]
        : d.id === "task"
          ? index === 1 && !failed
            ? [`${spanPrefix}0004`, answerId]
            : [answerId, toolId]
          : [toolId],
  }));
  if (runPrefix === "baseline")
    for (const s of spans) s.started_at = s.started_at.replace("T08:", "T07:");
  return {
    id,
    case_id: c.case_id,
    title: c.title,
    category: c.categories[0],
    case_hash: c.content_hash,
    execution_status: error ? "timeout" : "completed",
    verdict,
    latency_ms: duration,
    tokens: error ? null : 600 + index * 63,
    cost: null,
    output: error ? null : finalOutput,
    error: error ? "工具执行超时，未产生最终输出。" : null,
    trace_id:
      (runPrefix === "candidate" ? "a" : "b") +
      String(index + 1).padStart(31, "0"),
    spans,
    grades,
  };
}
const common = {
  origin: "fixture" as const,
  agent_name: "本地 Python 智能体",
  dataset_id: sampleDataset.id,
  dataset_version: 1,
  rubric_id: sampleRubric.id,
  rubric_version: 1,
  total_dataset_cases: 12,
  status: "completed" as const,
};
export const sampleBaseline: EvaluationRun = {
  ...common,
  id: "example-baseline",
  name: "基线运行",
  agent_version: "fixture-baseline",
  created_at: "2026-11-05T07:00:00Z",
  trials: (
    [
      "pass",
      "pass",
      "fail",
      "pass",
      "pass",
      "pending_review",
      "ungraded",
      "pass",
    ] as Verdict[]
  ).map((v, i) => makeTrial(i, v, "baseline")),
};
export const sampleCandidate: EvaluationRun = {
  ...common,
  id: "example-candidate",
  name: "候选运行",
  agent_version: "fixture-candidate",
  created_at: "2026-11-05T08:00:00Z",
  trials: (
    [
      "pass",
      "fail",
      "pass",
      "pass",
      "fail",
      "pending_review",
      "ungraded",
      "pass",
    ] as Verdict[]
  ).map((v, i) => makeTrial(i, v, "candidate")),
};
export const sampleRuns: EvaluationRun[] = [sampleCandidate, sampleBaseline];
