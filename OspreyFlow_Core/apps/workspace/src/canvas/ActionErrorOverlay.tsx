import { Popover } from "../design/primitives/Popover";

export interface ActionErrorOverlayProps {
  x: number;
  y: number;
  message: string;
  onClose: () => void;
  /** `error` (the default) is a call that failed; `notice` is a call that worked and has nothing to
   * show, which is not an error and must not read as one (ADR-077). */
  tone?: "error" | "notice";
}

/** `expandNode`/`manualAssertion`/`explainCluster` (`GlassCanvas.tsx`) used to drop a failed call
 * silently (`if (!response.ok) return;`) behind a comment claiming it "surfaces via a Toast at
 * the App layer" — checked directly and found false: the App-layer Toast is driven only by
 * what the App sets itself, never by a client-side `fetch` failure, so
 * none of the three ever actually reached the analyst. `manualAssertion` was the priority to fix:
 * `expandNode`/`explainCluster` are failed *reads* that mislead an analyst about what the data
 * shows; a failed `manualAssertion` is a failed *write* that leaves the analyst believing a link
 * (or split) is recorded in the case when it is not — the more dangerous silence of the three.
 * Same shape `PathfinderErrorOverlay` already established for `findPaths`: `role="alert"` so
 * assistive technology announces it the moment it mounts, dismissed via the same `Popover`
 * Escape-dismiss every other canvas overlay already uses. A separate component from
 * `PathfinderErrorOverlay` rather than a shared one — the pathfinder's own error is one of two
 * distinguishable outcomes (search failed vs. search completed with no results); these three have
 * no analogous second outcome to distinguish from, so one generic "the action did not complete"
 * overlay covers all three. */
export function ActionErrorOverlay({ x, y, message, onClose, tone = "error" }: ActionErrorOverlayProps) {
  const isNotice = tone === "notice";
  return (
    <Popover x={x} y={y} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 240 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong
            className="value"
            role={isNotice ? "status" : "alert"}
            style={isNotice ? undefined : { color: "var(--error)" }}
          >
            {message}
          </strong>
          <button
            type="button"
            className="icon-btn"
            aria-label={isNotice ? "Close message" : "Close error"}
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </div>
    </Popover>
  );
}
