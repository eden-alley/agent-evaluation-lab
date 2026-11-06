"use client";
import { useEffect, useRef, useState } from "react";
import { BookOpen, Plus, ArrowUpRight } from "lucide-react";
import { qualityApi } from "../lib/quality-api";
import type { Skill } from "../lib/quality-types";
import { Header } from "./report-ui";

export function Skills() {
  const [items, setItems] = useState<Skill[]>([]),
    [selected, setSelected] = useState<Skill | null>(null);
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [creating, setCreating] = useState(false);
  const [name, setName] = useState(""),
    [description, setDescription] = useState(""),
    [kind, setKind] = useState<"evaluation" | "business">("business");
  const [content, setContent] = useState(""),
    [note, setNote] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const epoch = useRef(0);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setItems((await qualityApi.skills()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    const initial = new URLSearchParams(window.location.search).get("skill");
    if (initial) void select(initial);
  }, []);
  async function select(id: string) {
    const request = ++epoch.current;
    setSelected(null);
    setContent("");
    setNote("");
    setError("");
    setMessage("");
    setDetailLoading(true);
    try {
      const skill = await qualityApi.skill(id);
      if (request !== epoch.current) return;
      setSelected(skill);
      setContent(skill.versions?.[0]?.content || "");
    } catch (e) {
      if (request === epoch.current)
        setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (request === epoch.current) setDetailLoading(false);
    }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const skill = await qualityApi.createSkill({
        name,
        description,
        kind,
        tags: [],
      });
      setItems((old) => [...old, skill]);
      setCreating(false);
      setName("");
      setDescription("");
      await select(skill.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await qualityApi.saveSkill(selected.id, content, note);
      const next = await qualityApi.skill(selected.id);
      setSelected(next);
      setContent(next.versions?.[0]?.content || "");
      setNote("");
      setMessage(saved.status === "published" ? "内容未变化，已发布版本保持不变。" : "内容已保存为版本草稿，尚未对外发布。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function publish(version: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const next = await qualityApi.publishSkill(selected.id, version);
      setSelected(next);
      setItems((old) => old.map((s) => (s.id === next.id ? next : s)));
      setMessage("技能版本已发布，外部 Agent 现在可发现和读取。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  }
  const unsaved =
    selected && (content !== (selected.versions?.[0]?.content || "") || !!note);
  return (
    <>
      <Header
        title="内置技能"
        desc="沉淀评测集设计与业务方法，由外部 Coding Agent 根据需求选用。"
        action={
          <button
            className="button primary"
            disabled={busy}
            onClick={() => setCreating(!creating)}
          >
            <Plus size={16} />
            新建技能
          </button>
        }
      />
      <div className="notice section-bottom">
        技能的方法内容由你共同设计和确认。未发布的草稿不会提供给外部
        Agent；平台不会自动生成技能内容。
      </div>
      {error && (
        <div role="alert" className="error section-bottom">
          {error}
          <button className="button small" onClick={load}>
            重试
          </button>
        </div>
      )}
      {message && (
        <div role="status" className="notice section-bottom">
          {message}
        </div>
      )}
      {creating && (
        <form className="panel pad stack section-bottom" onSubmit={create}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="skill-name">技能名称</label>
              <input
                id="skill-name"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={160}
                disabled={busy}
              />
            </div>
            <div className="field">
              <label htmlFor="skill-kind">类型</label>
              <select
                id="skill-kind"
                className="input"
                value={kind}
                onChange={(e) => setKind(e.target.value as typeof kind)}
                disabled={busy}
              >
                <option value="business">业务技能</option>
                <option value="evaluation">评测技能</option>
              </select>
            </div>
          </div>
          <div className="field">
            <label htmlFor="skill-description">适用任务与说明</label>
            <textarea
              id="skill-description"
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              disabled={busy}
            />
          </div>
          <div className="row">
            <button className="button primary" disabled={busy}>
              创建目录项
            </button>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => setCreating(false)}
            >
              取消
            </button>
          </div>
        </form>
      )}
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>技能目录</h2>
            <p>
              {items.filter((s) => s.active_version).length} 个已发布 /{" "}
              {items.length} 个目录项
            </p>
          </div>
          <a className="click small" href="/settings">
            连接外部 Agent <ArrowUpRight size={12} className="inline-icon" />
          </a>
        </div>
        {loading ? (
          <p className="pad muted">正在加载…</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>技能</th>
                  <th>类型</th>
                  <th>当前状态</th>
                  <th>来源</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((skill) => (
                  <tr
                    key={skill.id}
                    className={selected?.id === skill.id ? "selected" : ""}
                  >
                    <td>
                      <strong>{skill.name}</strong>
                      <p className="small muted table-description">
                        {skill.description}
                      </p>
                    </td>
                    <td>
                      {skill.kind === "evaluation" ? "评测方法" : "业务方法"}
                    </td>
                    <td>
                      <span
                        className={
                          "badge " + (skill.active_version ? "good" : "warn")
                        }
                      >
                        {skill.active_version
                          ? `已发布 v${skill.active_version.version}`
                          : "待共创"}
                      </span>
                    </td>
                    <td>
                      {skill.origin === "builtin" ? "内置目录" : "用户创建"}
                    </td>
                    <td>
                      <button
                        className="button small"
                        disabled={busy}
                        onClick={() => select(skill.id)}
                      >
                        查看与编辑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {detailLoading && (
        <p role="status" className="pad muted">
          正在读取技能…
        </p>
      )}
      {selected && (
        <div className="skill-editor section-gap">
          <form className="panel" onSubmit={save}>
            <div className="panel-head">
              <div>
                <h2 className="row">
                  <BookOpen size={17} />
                  {selected.name}
                </h2>
                <p>保存会生成新版本草稿，已发布版本保持不变。</p>
              </div>
            </div>
            <div className="pad stack">
              <div className="field">
                <label htmlFor="skill-content">技能内容</label>
                <textarea
                  id="skill-content"
                  className="input mono skill-content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="在这里填写共同设计的技能方法与适用说明。"
                  required
                  disabled={busy}
                />
              </div>
              <div className="field">
                <label htmlFor="skill-change-note">本次修改说明</label>
                <input
                  id="skill-change-note"
                  className="input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="row">
                <button
                  className="button primary"
                disabled={busy || !content.trim() || !unsaved}
                >
                  保存版本草稿
                </button>
                {unsaved && (
                  <span className="small muted">编辑内容尚未保存</span>
                )}
              </div>
            </div>
          </form>
          <div className="panel">
            <div className="panel-head">
              <div>
                <h2>版本记录</h2>
                <p>发布后供外部 Agent 按需读取。</p>
              </div>
            </div>
            <div className="pad stack">
              {!selected.versions?.length && (
                <p className="muted">
                  尚无内容版本。当前仅保留目录项，等待共同设计。
                </p>
              )}
              {selected.versions?.map((v) => (
                <div className="version-entry" key={v.id}>
                  <div className="row between">
                    <strong>v{v.version}</strong>
                    <span
                      className={
                        "badge " + (v.status === "published" ? "good" : "warn")
                      }
                    >
                      {v.status === "published" ? "已发布" : "草稿"}
                    </span>
                  </div>
                  <p className="small muted">
                    {new Date(v.created_at).toLocaleString("zh-CN")} ·{" "}
                    {v.change_note || "无修改说明"}
                  </p>
                  <details>
                    <summary>查看此版本内容与哈希</summary>
                    <pre className="code">{v.content}</pre>
                    <p className="mono break-word">{v.content_hash}</p>
                  </details>
                  {v.status === "draft" && (
                    <button
                      type="button"
                      className="button small"
                      disabled={busy || !!unsaved}
                      onClick={() => publish(v.id)}
                    >
                      发布此版本
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
