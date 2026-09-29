import type { CSSProperties } from "react";

import { CHANNEL_HEX, FALLBACK_CHANNEL_HEX } from "../color/tokens";
import type { OntologyRegistry } from "../ontology/schema";
import type { DocumentView, MessageSpan } from "./models";

export interface HighlightedMessageProps {
  document: DocumentView;
  ontology: OntologyRegistry;
  onSelectNode?: (nodeId: string) => void;
}

interface Run {
  text: string;
  span: MessageSpan | null;
}

/** Splits `text` at each (already principal-narrowed, already sorted) span boundary into
 * alternating plain/highlighted runs — a span the backend never returned (because its own node
 * was not visible, `services/api/dossier.py`'s own leak defence) simply never produces a run
 * here; there is no "redacted" run to render, only plain, undecorated text indistinguishable
 * from prose nothing was ever extracted from. */
function splitIntoRuns(text: string, spans: MessageSpan[]): Run[] {
  const runs: Run[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start > cursor) runs.push({ text: text.slice(cursor, span.start), span: null });
    runs.push({ text: text.slice(span.start, span.end), span });
    cursor = span.end;
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
    backgroundColor: `color-mix(in srgb, ${hex} 8%, transparent)`,
    borderBottom: `2px ${provenanceState === "inferred" ? "dashed" : "solid"} ${hex}`,
    padding: "0 1px",
    cursor: "pointer",
    font: "inherit",
    color: "inherit",
  };
}

export function HighlightedMessage({ document, ontology, onSelectNode }: HighlightedMessageProps) {
  const runs = splitIntoRuns(document.text, document.spans);
  return (
    <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
      {runs.map((run, i) => {
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
