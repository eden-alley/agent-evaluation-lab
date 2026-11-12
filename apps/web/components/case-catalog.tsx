"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ChevronRight, FileText } from "lucide-react";
import {
  caseFiles,
  caseMessages,
  objectValue,
  textValue,
  type CatalogEntry,
} from "../lib/case-catalog";
import { json } from "./report-ui";
import styles from "./case-catalog.module.css";

// Emphasis changes typography only; the underlying text is never rewritten.
function Emphasis({ text }: { text: string }) {
  const pattern =
    /(`[^`]+`|\b\d[\d,]*(?:\.\d+)?\b|[\w./-]+\.(?:json|txt|md|csv|py)\b|最后一次修改|新规则|只允许写入一次|没有被重放|完整日志|全文|先澄清|不能擅自创建|去重|筛选|退款|验收反馈)/g;
  return text.split(pattern).map((part, i) =>
    i % 2 ? (
      part.startsWith("`") ? (
        <code key={i}>{part.slice(1, -1)}</code>
      ) : (
        <strong className={styles.emphasis} key={i}>
          {part}
        </strong>
      )
    ) : (
      part
    ),
  );
}

export function CaseCatalog({
  entries,
  overview,
  onReport,
}: {
  entries: CatalogEntry[];
  overview?: string;
  onReport: (draftId: string) => void;
}) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null),
    detailScroller = useRef<HTMLDivElement>(null),
    backButton = useRef<HTMLButtonElement>(null);
  const rowButtons = useRef(new Map<string, HTMLButtonElement>());
  const listScroll = useRef(0),
    lastKey = useRef<string | null>(null);
  const selectedIndex = entries.findIndex((entry) => entry.key === selectedKey);
  const selected = entries[selectedIndex];
  const groups = [
    ...new Set(entries.map((entry) => entry.presentation.displayGroup)),
  ];
  const allUnrun =
    entries.length > 0 &&
    entries.every((entry) => entry.item.input.run_status === "not_run");

  useEffect(() => {
    if (selectedKey && !selected) setSelectedKey(null);
    if (selected) {
      if (detailScroller.current) detailScroller.current.scrollTop = 0;
      backButton.current?.focus({ preventScroll: true });
    } else if (lastKey.current) {
      if (scroller.current) scroller.current.scrollTop = listScroll.current;
      rowButtons.current.get(lastKey.current)?.focus({ preventScroll: true });
    }
  }, [selectedKey, selected]);

  function open(entry: CatalogEntry) {
    if (!selected) listScroll.current = scroller.current?.scrollTop || 0;
    lastKey.current = entry.key;
    setSelectedKey(entry.key);
  }
  function close() {
    setSelectedKey(null);
  }

  return (
    <section
      className={styles.catalog}
      aria-label="评测题库"
      onKeyDown={(e) => {
        if (e.key === "Escape" && selected) close();
      }}
    >
      <div hidden={!!selected}>
        <div className={styles.heading}>
          <h2>评测题库</h2>
          <p>
            {entries.length} 道题{allUnrun ? " · 尚未运行" : ""}
          </p>
        </div>
        {overview && <p className={styles.catalogIntro}>{overview}</p>}
        {entries.length ? (
          <>
            <div
              className={styles.scroll}
              ref={scroller}
              aria-label="按类型分组的评测题目"
            >
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">评测题目</th>
                    <th scope="col">简介</th>
                    <th scope="col">重点考察</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map((group) => {
                    const items = entries.filter(
                      (entry) => entry.presentation.displayGroup === group,
                    );
                    return (
                      <Fragment key={group}>
                        <tr
                          className={styles.group}
                          data-tone={items[0].presentation.tone}
                        >
                          <th scope="rowgroup" colSpan={3}>
                            <strong>{group}</strong>
                            <span>{items.length} 道</span>
                          </th>
                        </tr>
                        {items.map((entry) => (
                          <tr
                            className={styles.question}
                            data-tone={entry.presentation.tone}
                            key={entry.key}
                            onClick={() => open(entry)}
                          >
                            <td>
                              <span className={styles.caseId}>
                                {entry.item.case_id.split("-")[0]}
                                {entry.presentation.difficulty
                                  ? ` · ${entry.presentation.difficulty}`
                                  : ""}
                              </span>
                              <button
                                type="button"
                                ref={(node) => {
                                  if (node)
                                    rowButtons.current.set(entry.key, node);
                                  else rowButtons.current.delete(entry.key);
                                }}
                                className={styles.open}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  open(entry);
                                }}
                                aria-label={`查看${entry.presentation.shortTitle}详情`}
                              >
                                {entry.presentation.shortTitle}
                              </button>
                            </td>
                            <td className={styles.description}>
                              <Emphasis text={entry.presentation.summary} />
                            </td>
                            <td>
                              <div className={styles.focus}>
                                <span>{entry.presentation.focus}</span>
                                <ChevronRight size={15} aria-hidden="true" />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className={styles.footer}>
              <span>点击题目，查看详细内容</span>
              <span>共 {entries.length} 道</span>
            </div>
          </>
        ) : (
          <div className="empty">
            <FileText size={28} className="empty-icon" />
            <h3>还没有评测题目</h3>
            <p>外部 Agent 提交草案后，题目会在这里按类型展示。</p>
          </div>
        )}
      </div>
      {selected && (
        <div data-tone={selected.presentation.tone}>
          <div className={styles.detailbar}>
            <button
              type="button"
              ref={backButton}
              className={styles.back}
              onClick={close}
            >
              <ArrowLeft size={15} />
              返回题库
            </button>
            <span>
              {selectedIndex + 1} / {entries.length}
            </span>
          </div>
          <div className={styles.detailScroll} ref={detailScroller}>
            <CaseContent
              key={selected.key}
              entry={selected}
              onReport={onReport}
            />
          </div>
          <div className={styles.footer}>
            <span>
              {selected.item.input.run_status === "not_run"
                ? "设计预览 · 尚未运行"
                : "用例设计 · 不代表运行成绩"}
            </span>
            <div className={styles.navigation}>
              <button
                type="button"
                disabled={selectedIndex === 0}
                onClick={() => open(entries[selectedIndex - 1])}
              >
                <ArrowLeft size={14} />
                上一题
              </button>
              <button
                type="button"
                disabled={selectedIndex === entries.length - 1}
                onClick={() => open(entries[selectedIndex + 1])}
              >
                下一题
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function CaseContent({
  entry,
  onReport,
}: {
  entry: CatalogEntry;
  onReport: (draftId: string) => void;
}) {
  const { item, draft, presentation: p } = entry;
  const metadata = objectValue(item.input.design_metadata);
  const messages = caseMessages(item),
    files = caseFiles(item);
  const sources = Array.isArray(metadata.sources)
    ? metadata.sources.filter((s): s is string => typeof s === "string")
    : [];
  const sourceLinks = Array.isArray(metadata.source_links)
    ? metadata.source_links
        .map(objectValue)
        .filter((s) => textValue(s.label) && textValue(s.location))
    : [];
  return (
    <div className={styles.content}>
      <h2>{p.shortTitle}</h2>
      <p className={styles.caseMeta}>
        {[item.case_id.split("-")[0], p.displayGroup, p.difficulty, p.readiness]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {p.scenario && p.task ? (
        <div className={styles.caseBrief}>
          <section>
            <h3>具体情景</h3>
            <p>
              <Emphasis text={p.scenario} />
            </p>
          </section>
          <section>
            <h3>要解决的问题</h3>
            <p>
              <Emphasis text={p.task} />
            </p>
          </section>
        </div>
      ) : (
        <p className={styles.intro}>{p.summary}</p>
      )}
      {p.acceptance && (
        <dl className={styles.overview}>
          <dt>怎样算完成</dt>
          <dd>{p.acceptance}</dd>
          <dt>考察点</dt>
          <dd>{p.focus}</dd>
        </dl>
      )}
      {p.notice && <div className={styles.warning}>{p.notice}</div>}
      {draft.status === "rejected" && (
        <div className={styles.warning}>
          该草案已退回修改。{draft.decision?.note}
        </div>
      )}
      {(p.preview.length > 0 || p.keyResult) && (
        <section className={styles.block}>
          <h3>题目预览</h3>
          <ol className={styles.steps}>
            {p.preview.map(([label, text], i) => (
              <li key={i}>
                <span className={styles.stepNumber}>{i + 1}</span>
                <div className={styles.stepLabel}>{label}</div>
                <p>
                  <Emphasis text={text} />
                </p>
              </li>
            ))}
          </ol>
          {p.keyResult && (
            <div className={styles.result}>
              <h3>关键判断</h3>
              <p>
                <Emphasis text={p.keyResult} />
              </p>
              {p.contrast && <p className={styles.contrast}>{p.contrast}</p>}
            </div>
          )}
          <p className={styles.sourceNote}>
            {p.curated
              ? "由原题压缩展示；完整任务与判据见下方。"
              : "任务原文节选；完整内容见下方。"}
          </p>
        </section>
      )}
      <section className={styles.block}>
        {(!p.acceptance || messages.length > 0) && (
          <details>
            <summary>
              {item.input.prompt_status === "sample"
                ? "查看题面样例"
                : "完整题目"}
              {messages.length ? ` · ${messages.length} 轮` : ""}
            </summary>
            <div className={styles.fold}>
              <h3>{item.title}</h3>
              {messages.length ? (
                messages.map((message, i) => (
                  <div className={styles.turn} key={i}>
                    <div className={styles.label}>
                      第 {message.index} 轮 ·{" "}
                      {message.role === "user"
                        ? "用户"
                        : message.role || "消息"}
                    </div>
                    <pre>{message.content}</pre>
                  </div>
                ))
              ) : (
                <pre>{json(item.input)}</pre>
              )}
            </div>
          </details>
        )}
        {!p.acceptance && (
          <details>
            <summary>判定依据与预期结果</summary>
            <div className={styles.fold}>
              <h3>评分说明</h3>
              <p className={styles.multiline}>
                {item.grading_notes || "未提供评分说明。"}
              </p>
              <details>
                <summary>查看完整预期结果</summary>
                <pre>{json(item.expected)}</pre>
              </details>
            </div>
          </details>
        )}
        {(files.length > 0 || !p.acceptance) && (
          <details>
            <summary>输入材料 · {files.length} 份</summary>
            <div className={styles.fold}>
              {textValue(metadata.size) && (
                <p className={styles.intro}>{textValue(metadata.size)}</p>
              )}
              {files.map((file, i) => (
                <details key={`${file.path}-${i}`}>
                  <summary className={styles.filename}>
                    {file.path}
                    {file.bytes !== null && (
                      <span> · {file.bytes.toLocaleString()} 字节</span>
                    )}
                  </summary>
                  <pre>{file.content}</pre>
                  {file.sha256 && (
                    <p className={styles.hash}>SHA-256 · {file.sha256}</p>
                  )}
                </details>
              ))}
              {!files.length && (
                <p className={styles.intro}>
                  未附带可展开的文件，请查看完整输入。
                </p>
              )}
            </div>
          </details>
        )}
        <details>
          <summary>来源、执行条件与原始数据</summary>
          <div className={styles.fold}>
            <p>{textValue(metadata.source_kind)}</p>
            {sources.map((source, i) => (
              <p className={styles.source} key={i}>
                {source}
              </p>
            ))}
            {sourceLinks.map((source, i) => (
              <p className={styles.source} key={i}>
                <strong>{textValue(source.label)}</strong>
                <br />
                {textValue(source.location)}
              </p>
            ))}
            {(
              [
                ["basis", "设计依据"],
                ["adaptation", "适配说明"],
                ["conditions", "执行条件"],
                ["limitations", "限制"],
              ] as const
            ).map(
              ([key, label]) =>
                textValue(metadata[key]) && (
                  <p className={styles.source} key={key}>
                    <strong>{label}：</strong>
                    {textValue(metadata[key])}
                  </p>
                ),
            )}
            {item.input.controller_protocol != null && (
              <details>
                <summary>执行控制协议</summary>
                <pre>
                  {typeof item.input.controller_protocol === "string"
                    ? item.input.controller_protocol
                    : json(item.input.controller_protocol)}
                </pre>
              </details>
            )}
            <details>
              <summary>完整提交内容</summary>
              <pre>{json(item)}</pre>
            </details>
            <p className={styles.source}>
              所属数据集：{draft.payload.name} ·{" "}
              {draft.status === "approved"
                ? "已确认"
                : draft.status === "rejected"
                  ? "已退回"
                  : "待审阅"}
            </p>
            <p className={styles.hash}>内容哈希 · {draft.content_hash}</p>
            <button
              type="button"
              className="button small"
              onClick={() => onReport(draft.id)}
            >
              查看质量报告与版本审阅
              <ChevronRight size={14} />
            </button>
          </div>
        </details>
      </section>
    </div>
  );
}
