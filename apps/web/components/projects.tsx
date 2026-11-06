"use client";
import { useEffect, useRef, useState } from "react";
import { FolderKanban, Plus } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type {
  AgentRegistration,
  AvailabilityReport,
  Project,
} from "../lib/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

export function Projects() {
  const [items, setItems] = useState<Project[]>([]),
    [selected, setSelected] = useState<Project | null>(null),
    [agent, setAgent] = useState<AgentRegistration | null>(null),
    [report, setReport] = useState<AvailabilityReport | null>(null);
  const [error, setError] = useState(""),
    [agentError, setAgentError] = useState(""),
    [message, setMessage] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [creating, setCreating] = useState(false),
    [editing, setEditing] = useState(false);
  const [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const [form, setForm] = useState({
    name: "",
    source_path: "",
    python_executable: "",
    entrypoint: "",
  });
  const dirty =
    !!agent &&
    (form.name !== agent.name ||
      form.source_path !== agent.source_path ||
      form.python_executable !== agent.python_executable ||
      form.entrypoint !== agent.entrypoint);
  function editField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setReport(null);
    setMessage("");
  }
  const requestId = useRef(0);
  const [agentLoad, setAgentLoad] = useState<"loading" | "ready" | "error">(
    "ready",
  );
  async function load() {
    setLoading(true);
    setError("");
    try {
      const result = await api.projects();
      setItems(result.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function select(project: Project) {
    const current = ++requestId.current;
    setSelected(project);
    setAgent(null);
    setReport(null);
    setAgentError("");
    setEditing(false);
    setForm({
      name: "",
      source_path: "",
      python_executable: "",
      entrypoint: "",
    });
    setAgentLoad("loading");
    try {
      const a = await api.agent(project.id);
      if (current !== requestId.current) return;
      setAgent(a);
      setReport(a.last_check);
      setForm({
        name: a.name,
        source_path: a.source_path,
        python_executable: a.python_executable,
        entrypoint: a.entrypoint,
      });
      setAgentLoad("ready");
    } catch (e) {
      if (current !== requestId.current) return;
      if (e instanceof ApiError && e.code === "AGENT_NOT_REGISTERED") {
        setAgentLoad("ready");
      } else {
        setAgentError(e instanceof Error ? e.message : "加载失败");
        setAgentLoad("error");
      }
    }
  }
  async function saveProject(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (editing && selected) {
        const project = await api.updateProject(selected.id, {
          name,
          description,
        });
        setItems(items.map((p) => (p.id === project.id ? project : p)));
        setSelected(project);
        setEditing(false);
      } else {
        const project = await api.createProject({ name, description });
        setItems([...items, project]);
        setCreating(false);
        await select(project);
      }
      setName("");
      setDescription("");
      setMessage("项目已保存。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function saveAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || agentLoad !== "ready") return;
    setBusy(true);
    setAgentError("");
    setMessage("");
    try {
      const a = await api.saveAgent(selected.id, {
        ...form,
        config: agent?.config ?? {},
      });
      setAgent(a);
      setReport(a.last_check);
      setMessage("智能体配置已保存。");
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    if (!selected || dirty) return;
    setBusy(true);
    setAgentError("");
    setMessage("");
    try {
      setReport(await api.checkAgent(selected.id));
      setMessage("配置检查已完成。");
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : "检查失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-head">
        <div>
          <h1>项目</h1>
          <p>
            说明用户需求与评测目标，并登记被测智能体；外部 Coding Agent
            从这里读取项目上下文。
          </p>
        </div>
        <Button
          variant="primary"
          disabled={busy}
          onClick={() => {
            setCreating(!creating);
            setEditing(false);
            setName("");
            setDescription("");
          }}
        >
          <Plus size={16} />
          新建项目
        </Button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}{" "}
          <button className="button small" onClick={load}>
            重试
          </button>
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      {(creating || editing) && (
        <div className="panel section-gap">
          <div className="panel-head">
            <h2>{editing ? "编辑项目" : "新建项目"}</h2>
          </div>
          <form className="pad stack" onSubmit={saveProject}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="project-name">项目名称</label>
                <input
                  id="project-name"
                  className="input"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="project-description">需求与评测目标</label>
                <input
                  id="project-description"
                  className="input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            </div>
            <div className="row">
              <button className="button primary" disabled={busy}>
                {busy ? "保存中…" : "保存项目"}
              </button>
              <button
                type="button"
                className="button"
                onClick={() => {
                  setCreating(false);
                  setEditing(false);
                }}
              >
                取消
              </button>
            </div>
          </form>
        </div>
      )}
      <div className="panel section-gap">
        <div className="panel-head">
          <div>
            <h2>项目列表</h2>
            <p>{items.length} 个项目 · 数据保存在本地工作区</p>
          </div>
        </div>
        {loading ? (
          <div className="pad muted">正在加载…</div>
        ) : items.length === 0 ? (
          <div className="empty">
            <FolderKanban size={30} className="empty-icon" />
            <h2>还没有项目</h2>
            <p>创建一个项目，登记本地智能体 配置并检查所需路径。</p>
            <button className="button" onClick={() => setCreating(true)}>
              创建第一个项目
            </button>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>描述</th>
                  <th>更新时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((project) => (
                  <tr
                    key={project.id}
                    className={selected?.id === project.id ? "selected" : ""}
                  >
                    <td>
                      <Button
                        variant="link"
                        disabled={busy}
                        onClick={() => select(project)}
                      >
                        {project.name}
                      </Button>
                    </td>
                    <td className="muted">{project.description || "—"}</td>
                    <td className="muted">
                      {new Date(project.updated_at).toLocaleString("zh-CN")}
                    </td>
                    <td>
                      <Button
                        size="small"
                        disabled={busy}
                        onClick={() => select(project)}
                      >
                        查看配置
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {selected && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>{selected.name} · 被测智能体配置</h2>
              <p>
                这里登记被评测的程序。外部 Coding Agent 的平台接入位于设置页。
              </p>
            </div>
            <Button
              size="small"
              disabled={busy}
              onClick={() => {
                setName(selected.name);
                setDescription(selected.description);
                setEditing(true);
                setCreating(false);
              }}
            >
              编辑项目
            </Button>
          </div>
          <form className="pad stack" onSubmit={saveAgent}>
            {agentLoad === "loading" && (
              <p className="muted" role="status">
                正在加载智能体配置…
              </p>
            )}
            {agentError && (
              <div className="error" role="alert">
                {agentError}{" "}
                <Button
                  type="button"
                  size="small"
                  onClick={() => select(selected)}
                >
                  重试
                </Button>
              </div>
            )}
            <fieldset
              disabled={busy || agentLoad !== "ready"}
              className="form-grid"
              style={{ border: 0, padding: 0, margin: 0 }}
            >
              <Field
                label="智能体名称"
                id="agent-name"
                value={form.name}
                set={(v) => editField("name", v)}
              />
              <Field
                label="源码目录"
                id="source-path"
                value={form.source_path}
                set={(v) => editField("source_path", v)}
                placeholder="例如 D:\\agent"
              />
              <Field
                label="Python 解释器路径"
                id="python-path"
                value={form.python_executable}
                set={(v) => editField("python_executable", v)}
              />
              <Field
                label="入口文件（相对源码目录）"
                id="entrypoint"
                value={form.entrypoint}
                set={(v) => editField("entrypoint", v)}
                placeholder="例如 agent.py"
              />
            </fieldset>
            <p className="small muted">
              请勿在配置中保存凭据。路径可以先登记，再进行检查。
            </p>
            <div className="row">
              <Button
                variant="primary"
                disabled={busy || agentLoad !== "ready"}
              >
                {busy ? "处理中…" : "保存智能体"}
              </Button>
              {agent && (
                <Button
                  type="button"
                  disabled={busy || agentLoad !== "ready" || dirty}
                  onClick={check}
                >
                  {dirty ? "请先保存配置" : "检查配置"}
                </Button>
              )}
            </div>
            {report && (
              <div className="notice">
                <div className="row between">
                  <strong>
                    配置
                    {report.configuration_status === "ready"
                      ? "路径就绪"
                      : "不可用"}
                  </strong>
                  <span className="badge warn">运行状态：未测试</span>
                </div>
                <p className="small" style={{ marginTop: 8 }}>
                  检查时间：
                  {new Date(report.checked_at).toLocaleString("zh-CN")}
                  。路径就绪不代表运行已验证。
                </p>
                <ul>
                  {report.checks.map((c, i) => (
                    <li key={i}>
                      {c.status === "pass" ? "通过" : "未通过"} ·{" "}
                      {(
                        {
                          source_path: "源码目录",
                          python_executable: "Python 解释器",
                          entrypoint: "入口文件",
                        } as Record<string, string>
                      )[c.name] || c.name}
                      ：{c.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </form>
        </div>
      )}
    </>
  );
}
function Field({
  label,
  id,
  value,
  set,
  placeholder,
}: {
  label: string;
  id: string;
  value: string;
  set: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <Input
        id={id}
        required
        value={value}
        placeholder={placeholder}
        onChange={(e) => set(e.target.value)}
      />
    </div>
  );
}
