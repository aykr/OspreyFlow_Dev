export interface StatusBarProps {
  nodeCount: number;
  edgeCount: number;
  dimmedCount: number;
  filteredCount: number;
}

/** `docs/02_GLASS_FRONTEND.md` §2: "12,481 nodes · 38,902 edges · 214
 * dimmed by filter · 6 hidden by handling ⓘ" — and its own rule 4: "The
 * status bar never lies... An analyst must never be able to mistake a
 * filtered picture for a complete one."
 *
 * `nodeCount`/`edgeCount` come from `graph.order`/`graph.size` — the
 * store's actual membership. `filteredCount` comes verbatim from the
 * server (`WorkingSetStoreState.filteredCount`, set only by a
 * `DeltaSnapshot`/accumulated from a `DeltaNotice`) — never recomputed
 * client-side (`docs/07_BUILD_PLAN.md` Phase 4's own stated constraint:
 * a client-side recount would silently diverge from a stale view). */
export function StatusBar({ nodeCount, edgeCount, dimmedCount, filteredCount }: StatusBarProps) {
  return (
    <div
      role="status"
      className="value"
      style={{
        display: "flex",
        gap: "var(--sp-12)",
        padding: "var(--sp-8) var(--sp-16)",
        borderTop: "1px solid var(--border-subtle)",
        color: "var(--text-secondary)",
        fontSize: "var(--fs-13)",
      }}
    >
      <span>{nodeCount.toLocaleString()} nodes</span>
      <span>{edgeCount.toLocaleString()} edges</span>
      <span>{dimmedCount.toLocaleString()} dimmed by filter</span>
      <span>{filteredCount.toLocaleString()} hidden by handling</span>
    </div>
  );
}
