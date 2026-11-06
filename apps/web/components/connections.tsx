"use client";
import { useEffect, useState } from "react";
import { Cable, Copy, Check, ArrowRight } from "lucide-react";
import { qualityApi } from "../lib/quality-api";
import type { Integration } from "../lib/quality-types";

export function Connections() {
  const [data, setData] = useState<Integration | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await qualityApi.integration());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(data.startup, null, 2),
      );
      setCopied(true);
    } catch {
      setError("无法自动复制，请选中配置文本手动复制。");
    }
  }
  return (
    <div className="panel section-gap">
      <div className="panel-head">
        <div>
          <h2 className="row">
            <Cable size={18} /> 外部 Coding Agent 接入
          </h2>
          <p>在你的编程助手中使用平台工具；平台不启动或替代编程助手。</p>
        </div>
        <button className="button small" onClick={load} disabled={loading}>
          刷新连接记录
        </button>
      </div>
      {error && (
        <div className="pad">
          <div className="error" role="alert">
            {error}
          </div>
        </div>
      )}
      {loading ? (
        <p className="pad muted">正在读取接入信息…</p>
      ) : (
        data && (
          <div className="pad stack">
            <div className="workflow-strip">
              <span>用户需求</span>
              <ArrowRight size={14} />
              <a href="/skills">按需选用技能</a>
              <ArrowRight size={14} />
              <span>外部 Agent 生成草案</span>
              <ArrowRight size={14} />
              <a href="/datasets">平台审阅与版本</a>
            </div>
            <div className="connection-grid">
              <div className="stack">
                <div>
                  <h3>1. 添加本地 MCP 服务</h3>
                  <p className="small muted section-note">
                    将下面的启动字段填入外部客户端的 MCP
                    配置。平台服务需保持运行。
                  </p>
                </div>
                <pre className="code connection-code">
                  {JSON.stringify(data.startup, null, 2)}
                </pre>
                <button className="button" onClick={copy}>
                  {copied ? <Check size={15} /> : <Copy size={15} />}{" "}
                  {copied ? "已复制" : "复制启动配置"}
                </button>
              </div>
              <div className="stack">
                <div>
                  <h3>2. 在外部 Agent 中调用工具</h3>
                  <p className="small muted section-note">
                    先读取项目和已发布技能，再提交草案及报告。平台工具不会执行模型调用。
                  </p>
                </div>
                <div className="connection-status">
                  <span className="badge info">
                    {data.protocol} · {data.transport}
                  </span>
                  <h3>
                    {data.last_call ? "已收到工具请求" : "尚未收到工具请求"}
                  </h3>
                  {data.last_call ? (
                    <>
                      <p className="small muted">
                        最近请求：
                        {new Date(data.last_call.created_at).toLocaleString(
                          "zh-CN",
                        )}
                      </p>
                      <p className="mono">
                        {data.last_call.tool} · HTTP{" "}
                        {data.last_call.status_code}
                      </p>
                      <p className="small muted">
                        客户端自报名称：{data.last_call.client}
                      </p>
                    </>
                  ) : (
                    <p className="small muted">
                      完成客户端配置后，调用 get_platform_status 验证接入。
                    </p>
                  )}
                  <p className="small muted">
                    此记录表示历史工具请求，不代表客户端当前在线。
                  </p>
                </div>
                <details>
                  <summary>查看 {data.tool_names.length} 个可用工具</summary>
                  <ul className="tool-list">
                    {data.tool_names.map((t) => (
                      <li className="mono" key={t}>
                        {t}
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            </div>
            <p className="small muted">
              {data.skill_policy}{" "}
              审阅确认在网页中进行，工具不提供发布数据集或技能的操作。
            </p>
          </div>
        )
      )}
    </div>
  );
}
