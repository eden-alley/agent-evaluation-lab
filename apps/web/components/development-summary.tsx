import React from "react";
import type { Recommendation } from "../lib/comparisons";

export function DevelopmentSummary({
  recommendations,
  onOpen,
  onCase,
  className,
}: {
  recommendations: Recommendation[];
  noRecommendationReason?: string | null;
  onOpen: () => void;
  onCase: (id: string) => void;
  className?: string;
}) {
  const first = recommendations[0];
  if (!first) return null;
  return (
    <section className={className} aria-label="下一步开发方向">
      <h2>{`优先方向：${first.title}`}</h2>
      <>
        <p>
          {first.action.match(/^.*?[。；]/)?.[0].replace(/；$/, "。") ??
            first.action}
        </p>
        <p>
          <strong>为什么优先：</strong>
          {first.priority_reason}
        </p>
        <div>
          {Array.from(new Set(first.refs.map((r) => r.case_id))).map((cid) => (
            <button
              className="button small"
              key={cid}
              onClick={() => onCase(cid)}
            >
              {cid} 经过
            </button>
          ))}
          <button className="button small" onClick={onOpen}>
            查看建议详情
          </button>
        </div>
      </>
    </section>
  );
}
