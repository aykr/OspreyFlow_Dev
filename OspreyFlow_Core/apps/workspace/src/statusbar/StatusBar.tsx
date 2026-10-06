import { Fragment } from "react";

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
  // ADR-097 step 3: each count a pair, the number a literal value in mono beside its words, with a
  // quiet separator between pairs.
  return (
    <div role="status" className="status-bar">
      {pairs.map(([count, words], i) => (
        <Fragment key={words}>
          {i > 0 && (
            <span className="status-pair__sep" aria-hidden="true">
              ·
            </span>
          )}
          <span className="status-pair">
            <span className="value">{count.toLocaleString("en-GB")}</span> {words}
          </span>
        </Fragment>
      ))}
    </div>
  );
}
