import type {
  Comparison,
  ComparisonRow,
  DatasetCase,
  EvaluationRun,
  JsonlValidation,
  RunSummary,
  DimensionSummary,
} from "./types";

export function summarizeDimensions(run: EvaluationRun): DimensionSummary[] {
  const dimensions = new Map<string, string>();
  for (const trial of run.trials)
    for (const grade of trial.grades)
      dimensions.set(grade.dimension_id, grade.name);
  return [...dimensions].map(([id, name]) => {
    const values = run.trials.flatMap((t) =>
      t.grades
        .filter(
          (g) =>
            g.dimension_id === id && g.status === "scored" && g.score !== null,
        )
        .map((g) => g.score as number),
    );
    return {
      id,
      name,
      mean: values.length
        ? values.reduce((a, b) => a + b, 0) / values.length
        : null,
      scored: values.length,
      selected: run.trials.length,
    };
  });
}

export function summarizeRun(run: EvaluationRun): RunSummary {
  const trials = run.trials;
  const selected = trials.length;
  const finished = trials.filter((t) =>
    ["completed", "error", "timeout"].includes(t.execution_status),
  ).length;
  const passed = trials.filter((t) => t.verdict === "pass").length;
  const failed = trials.filter((t) => t.verdict === "fail").length;
  const scored = passed + failed;
  const latencies = trials
    .map((t) => t.latency_ms)
    .filter((n): n is number => n !== null);
  const tokens = trials
    .map((t) => t.tokens)
    .filter((n): n is number => n !== null);
  const costs = trials
    .map((t) => t.cost)
    .filter((n): n is number => n !== null);
  return {
    selected,
    finished,
    scored,
    passed,
    failed,
    pending: trials.filter((t) => t.verdict === "pending_review").length,
    execution_errors: trials.filter((t) =>
      ["error", "timeout"].includes(t.execution_status),
    ).length,
    execution_coverage: selected ? finished / selected : null,
    grading_coverage: selected ? scored / selected : null,
    pass_rate: scored ? passed / scored : null,
    average_latency_ms: latencies.length
      ? latencies.reduce((a, b) => a + b, 0) / latencies.length
      : null,
    latency_coverage: latencies.length,
    total_tokens:
      selected && tokens.length === selected
        ? tokens.reduce((a, b) => a + b, 0)
        : null,
    token_coverage: tokens.length,
    total_cost:
      selected && costs.length === selected
        ? costs.reduce((a, b) => a + b, 0)
        : null,
    cost_coverage: costs.length,
  };
}

export function compareRuns(
  baseline: EvaluationRun,
  candidate: EvaluationRun,
): Comparison {
  const reason =
    baseline.dataset_id !== candidate.dataset_id
      ? "数据集不同，不能直接归因于智能体的变化。"
      : baseline.rubric_id !== candidate.rubric_id ||
          baseline.rubric_version !== candidate.rubric_version
        ? "评分规则版本不同，仅并列展示结果。"
        : null;
  const a = new Map(baseline.trials.map((t) => [t.case_id, t]));
  const b = new Map(candidate.trials.map((t) => [t.case_id, t]));
  const ids = [...new Set([...a.keys(), ...b.keys()])];
  const rows: ComparisonRow[] = ids.map((case_id) => {
    const before = a.get(case_id) || null,
      after = b.get(case_id) || null;
    let change: ComparisonRow["change"] = "unchanged";
    if (reason) change = "incomparable";
    else if (!before) change = "added";
    else if (!after) change = "removed";
    else if (before.case_hash !== after.case_hash) change = "modified";
    else if (
      !["pass", "fail"].includes(before.verdict) ||
      !["pass", "fail"].includes(after.verdict)
    )
      change = "ungraded";
    else if (before.verdict === "pass" && after.verdict === "fail")
      change = "regressed";
    else if (before.verdict === "fail" && after.verdict === "pass")
      change = "fixed";
    return {
      case_id,
      title: after?.title || before?.title || case_id,
      baseline: before,
      candidate: after,
      change,
    };
  });
  return {
    comparable: reason === null,
    reason,
    rows,
    regressions: rows.filter((r) => r.change === "regressed").length,
    fixes: rows.filter((r) => r.change === "fixed").length,
  };
}

const object = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
export function validateJsonl(text: string): JsonlValidation {
  const errors: JsonlValidation["errors"] = [];
  const cases: DatasetCase[] = [];
  const ids = new Set<string>();
  const keys = new Set([
    "schema_version",
    "case_id",
    "input",
    "expected",
    "categories",
    "metadata",
  ]);
  if (new TextEncoder().encode(text).byteLength > 5 * 1024 * 1024)
    return {
      valid: false,
      cases: [],
      errors: [{ line: 0, message: "预览文件不能超过 5 MiB。" }],
      categories: [],
    };
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    if (cases.length >= 10000) {
      errors.push({ line: i + 1, message: "单次预览最多 10,000 条用例。" });
      break;
    }
    let v: unknown;
    try {
      v = JSON.parse(lines[i]);
    } catch {
      errors.push({ line: i + 1, message: "不是有效的 JSON 对象。" });
      continue;
    }
    let message = "";
    if (!object(v)) message = "每行必须是一个对象。";
    else if (Object.keys(v).some((k) => !keys.has(k)))
      message = "存在未定义的顶层字段；扩展信息请放入 metadata。";
    else if (v.schema_version !== 1) message = "schema_version 必须为 1。";
    else if (typeof v.case_id !== "string" || !v.case_id.trim())
      message = "case_id 必须是非空字符串。";
    else if (ids.has(v.case_id.trim())) message = "case_id 重复。";
    else if (!object(v.input)) message = "input 必须是 JSON 对象。";
    else if (v.expected !== null && !object(v.expected))
      message = "expected 必须是 JSON 对象或 null。";
    else if (
      v.categories !== undefined &&
      (!Array.isArray(v.categories) ||
        v.categories.some((c) => typeof c !== "string" || !c.trim()))
    )
      message = "categories 必须是非空字符串组成的数组。";
    else if (v.metadata !== undefined && !object(v.metadata))
      message = "metadata 必须是 JSON 对象。";
    if (message) {
      errors.push({ line: i + 1, message });
      continue;
    }
    const row = v as Record<string, unknown>,
      id = (row.case_id as string).trim();
    ids.add(id);
    cases.push({
      case_id: id,
      title:
        object(row.metadata) && typeof row.metadata.title === "string"
          ? row.metadata.title
          : id,
      input: row.input as Record<string, unknown>,
      expected: row.expected as Record<string, unknown> | null,
      categories: (row.categories as string[] | undefined) || [],
      content_hash: "unversioned-preview",
    });
  }
  if (!cases.length && !errors.length)
    errors.push({ line: 0, message: "文件没有用例；请提供至少一行 JSON。" });
  return {
    valid: errors.length === 0,
    cases: errors.length ? [] : cases,
    errors,
    categories: errors.length
      ? []
      : [...new Set(cases.flatMap((c) => c.categories))],
  };
}
