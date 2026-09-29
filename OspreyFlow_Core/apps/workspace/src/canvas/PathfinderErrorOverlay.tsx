import { Popover } from "../design/primitives/Popover";

export interface PathfinderErrorOverlayProps {
  x: number;
  y: number;
  message: string;
  onClose: () => void;
}

/** `GlassCanvas.tsx`'s `findPaths` used to drop a failed `/v1/paths` call silently
 * (`if (!response.ok) return;`, raised twice with no owning phase before this fix) — in an
 * investigation tool that is worse than a UX defect: the analyst reads a missing overlay as "no
 * path exists" when the system in fact reached no conclusion at all, and absence of a result is
 * itself a finding `PathfinderOverlay`'s own "No path found" state already treats as one. This is
 * the distinguishable third state: not "found", not "searched and found nothing", but "did not
 * search to completion" — same transient `Popover` shape (and Escape-dismiss) `PathfinderOverlay`
 * already uses, `role="alert"` on the message so assistive technology announces it the moment it
 * mounts, not only via the dialog's own focus shift. */
export function PathfinderErrorOverlay({ x, y, message, onClose }: PathfinderErrorOverlayProps) {
  return (
    <Popover x={x} y={y} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 240 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong className="value" role="alert" style={{ color: "var(--error)" }}>
            {message}
          </strong>
          <button
            type="button"
            className="icon-btn"
            aria-label="Close pathfinder error"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </div>
    </Popover>
  );
}
