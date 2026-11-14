import React, { type ReactNode } from "react";
import type { CaseExplanation, Material } from "../lib/comparisons";

// Only paragraphs, inline code and fenced code are needed for archived stories.
// React escapes their contents; report text never becomes HTML.
function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split(/(```[^\n]*\n[\s\S]*?```)/g).map((block, index) => {
        if (block.startsWith("```")) {
          return (
            <pre className="code" key={index}>
              <code>
                {block
                  .replace(/^```[^\n]*\n/, "")
                  .replace(/```$/, "")
                  .trimEnd()}
              </code>
            </pre>
          );
        }
        return block
          .split(/\n\s*\n/)
          .filter((p) => p.trim())
          .map((p, n) => (
            <p key={`${index}-${n}`} style={{ whiteSpace: "pre-wrap" }}>
              {p
                .split(/(`[^`\n]+`)/g)
                .map((part, i) =>
                  part.startsWith("`") ? (
                    <code key={i}>{part.slice(1, -1)}</code>
                  ) : (
                    part
                  ),
                )}
            </p>
          ));
      })}
    </>
  );
}

export function TaskNarrative({
  explanation,
  renderEvidence,
}: {
  explanation: CaseExplanation;
  renderEvidence: (items: Material[]) => ReactNode;
}) {
  const [lead, ...acceptance] = explanation.result.text.split(/\n\s*\n/);
  return (
    <div style={{ maxWidth: 900, lineHeight: 1.85 }}>
      <p style={{ fontSize: "1.12rem" }}>
        <strong>{lead}</strong>
      </p>
      <Paragraphs text={explanation.background} />
      <h2 style={{ marginTop: 28 }}>实际经过</h2>
      {explanation.stages.map((stage, index) => (
        <article key={index} style={{ marginTop: 24 }}>
          <h3>{stage.title}</h3>
          <Paragraphs text={stage.text} />
          {renderEvidence(stage.evidence)}
        </article>
      ))}
      <h2 style={{ marginTop: 28 }}>最终验收</h2>
      {acceptance.length > 0 && <Paragraphs text={acceptance.join("\n\n")} />}
      {renderEvidence(explanation.result.evidence)}
    </div>
  );
}
