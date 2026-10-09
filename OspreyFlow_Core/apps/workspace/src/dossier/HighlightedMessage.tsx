import type { CSSProperties } from "react";

import { CHANNEL_HEX, FALLBACK_CHANNEL_HEX } from "../color/tokens";
import type { OntologyRegistry } from "../ontology/schema";
import type { DocumentView, MessageSpan } from "./models";

/** A finding not yet accepted, shown where it sits (ADR-098 Amendment 1): no node to select,
 * so no `node_id` and nothing to click — `pending` in the drawing sense rule 5 already uses,
 * dashed like any other inferred fact. */
export interface PendingHighlight {
  start: number;
  end: number;
  entity_type: string;
}

export interface HighlightedMessageProps {
  document: DocumentView;
  ontology: OntologyRegistry;
  onSelectNode?: (nodeId: string) => void;
  pending?: PendingHighlight[];
}

interface Run {
  text: string;
  span: MessageSpan | null;
  pending?: PendingHighlight | null;
}

/** Splits `text` at each (already principal-narrowed, already sorted) span boundary into
 * alternating plain/highlighted runs — a span the backend never returned (because its own node
 * was not visible, `services/api/dossier.py`'s own leak defence) simply never produces a run
 * here; there is no "redacted" run to render, only plain, undecorated text indistinguishable
 * from prose nothing was ever extracted from. */
function splitIntoRuns(text: string, spans: MessageSpan[], pending: PendingHighlight[]): Run[] {
  // An accepted span always wins the words: a pending one overlapping it is not drawn (it is
  // usually the same finding, just read again mid-acceptance), and the rest join in order.
  const shown: (Run & { at: number; to: number })[] = [
    ...spans.map((span) => ({ text: text.slice(span.start, span.end), span, at: span.start, to: span.end })),
    ...pending
      .filter((p) => !spans.some((s) => p.start < s.end && s.start < p.end))
      .map((p) => ({ text: text.slice(p.start, p.end), span: null, pending: p, at: p.start, to: p.end })),
  ].sort((a, b) => a.at - b.at);

  const runs: Run[] = [];
  let cursor = 0;
  for (const run of shown) {
    if (run.at > cursor) runs.push({ text: text.slice(cursor, run.at), span: null });
    runs.push(run);
    cursor = run.to;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor), span: null });
  return runs;
}

/** Phase 6a Stage 4 (B6) — never a solid channel fill behind text, which is exactly what would
 * risk the contrast floor: `02_GLASS_FRONTEND.md`'s own existing "8% channel opacity" convention
 * (already specified for the community-hull overlay) reused here via `color-mix`, a CSS-native,
 * already theme-aware equivalent of the canvas's own `mixOklab` dimming — text colour is never
 * touched, so there is no new foreground/background pairing for axe-core to evaluate. The run's
 * own border reuses `canvas/nodeAttributes.ts`'s `provenanceStroke` distinction (solid for
 * asserted, dashed for inferred) rather than a second visual language for the same fact. */
function highlightStyle(channel: string, provenanceState: MessageSpan["provenance_state"]): CSSProperties {
  const hex = CHANNEL_HEX[channel] ?? FALLBACK_CHANNEL_HEX;
  return {
    // 18%, raised from the hull convention's 8% (the owner, 9 October 2026: the types were too
    // hard to tell apart in the text). Text colour is still never touched, so the contrast-floor
    // argument above stands.
    backgroundColor: `color-mix(in srgb, ${hex} 18%, transparent)`,
    borderBottom: `2px ${provenanceState === "inferred" ? "dashed" : "solid"} ${hex}`,
    padding: "0 1px",
    cursor: "pointer",
    font: "inherit",
    color: "inherit",
  };
}

/** Which colour marks which entity type (the owner, 9 October 2026): one chip per type present,
 * drawn exactly as its highlights are, and the dashed meaning said when anything is pending. */
export function HighlightLegend({
  types,
  pendingPresent,
  ontology,
}: {
  types: readonly string[];
  pendingPresent: boolean;
  ontology: OntologyRegistry;
}) {
  if (types.length === 0) return null;
  return (
    <p
      aria-label="Highlight colours"
      className="label"
      style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-12)", alignItems: "center", margin: 0 }}
    >
      {types.map((type) => {
        const hex = CHANNEL_HEX[ontology.visualFor(type)?.channel ?? ""] ?? FALLBACK_CHANNEL_HEX;
        return (
          <span key={type} style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-4)" }}>
            <span
              aria-hidden="true"
              style={{
                width: "12px",
                height: "12px",
                borderRadius: "var(--r-control)",
                backgroundColor: `color-mix(in srgb, ${hex} 18%, transparent)`,
                borderBottom: `2px solid ${hex}`,
              }}
            />
            {type}
          </span>
        );
      })}
      {pendingPresent && <span>dashed: found, not yet accepted</span>}
    </p>
  );
}

export function HighlightedMessage({ document, ontology, onSelectNode, pending }: HighlightedMessageProps) {
  const runs = splitIntoRuns(document.text, document.spans, pending ?? []);
  return (
    <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
      {runs.map((run, i) => {
        if (run.pending) {
          const visual = ontology.visualFor(run.pending.entity_type);
          return (
            <span
              key={i}
              title={`${run.pending.entity_type} — found, not yet accepted`}
              style={{ ...highlightStyle(visual?.channel ?? "", "inferred"), cursor: "inherit" }}
            >
              {run.text}
            </span>
          );
        }
        if (!run.span) return <span key={i}>{run.text}</span>;
        const visual = ontology.visualFor(run.span.entity_type);
        return (
          <button
            key={i}
            type="button"
            style={highlightStyle(visual?.channel ?? "", run.span.provenance_state)}
            onClick={() => onSelectNode?.(run.span!.node_id)}
            title={run.span.entity_type}
          >
            {run.text}
          </button>
        );
      })}
    </p>
  );
}
