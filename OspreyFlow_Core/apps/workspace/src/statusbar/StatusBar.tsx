import { useState } from "react";

import { WORKSPACE_TIPS } from "./tips";

export interface StatusBarProps {
  nodeCount: number;
  edgeCount: number;
  dimmedCount: number;
  filteredCount: number;
  /** Nodes folded into Group Nodes by Communities, so counted but not drawn one by one. */
  groupedCount?: number;
}

/** `spec/02_GLASS_FRONTEND.md` §2: "12,481 nodes · 38,902 edges · 214
 * dimmed by filter · 6 hidden by handling ⓘ" — and its own rule 4: "The
 * status bar never lies... An analyst must never be able to mistake a
 * filtered picture for a complete one."
 *
 * `nodeCount`/`edgeCount` come from `graph.order`/`graph.size` — the
 * store's actual membership. `filteredCount` comes verbatim from the
 * server (`WorkingSetStoreState.filteredCount`, set only by a
 * `DeltaSnapshot`/accumulated from a `DeltaNotice`) — never recomputed
 * client-side (a stated constraint:
 * a client-side recount would silently diverge from a stale view). */
export function StatusBar({
  nodeCount,
  edgeCount,
  dimmedCount,
  filteredCount,
  groupedCount = 0,
}: StatusBarProps) {
  const pairs: [number, string][] = [
    [nodeCount, "nodes"],
    [edgeCount, "edges"],
    [dimmedCount, "dimmed by filter"],
    [filteredCount, "hidden by handling"],
    ...(groupedCount > 0 ? ([[groupedCount, "folded into groups"]] as [number, string][]) : []),
  ];
  const [tip, setTip] = useState(0);
  // ADR-097 step 3: each count a pair, the number a literal value in mono beside its words. ADR-115
  // E4: the pairs stand 16px apart with no separator, and a tip sits at the right, outside the live
  // counts so a new tip is not announced as a change to them.
  return (
    <div className="status-bar">
      <div role="status" className="status-bar__counts">
        {pairs.map(([count, words]) => (
          <span key={words} className="status-pair">
            <span className="value">{count.toLocaleString("en-GB")}</span> {words}
          </span>
        ))}
      </div>
      <section aria-label="Tip" className="status-bar__tip">
        <span className="status-bar__tip-label">Tip</span>
        <span>{WORKSPACE_TIPS[tip % WORKSPACE_TIPS.length]}</span>
        <button type="button" className="btn btn--quiet status-bar__next" onClick={() => setTip((t) => t + 1)}>
          Next tip
        </button>
      </section>
    </div>
  );
}
