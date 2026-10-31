// Where the empty canvas's "Where to start" panel (ADR-100) sits. Centred on the canvas, it ran under
// the workspace's welcome panel (ADR-115 E6, an overlay at the canvas's top left, above it) at 1440px:
// the welcome panel's 320px and the centred 28rem met over the left of the list, hiding "What this
// case holds" (seen 31 October 2026 under both brands). With the welcome panel open it is centred in
// the room to that panel's right instead.
import type { CSSProperties } from "react";

/** The welcome panel's width and its left gap: the room it takes from the canvas's left. */
const WELCOME_ROOM = "(var(--w-welcome-panel) + var(--sp-8))";

export function exploreOverlayPlace(welcomeOpen: boolean): Pick<CSSProperties, "left" | "width"> {
  if (!welcomeOpen) return { left: "50%", width: "min(28rem, calc(100% - var(--sp-32)))" };
  return {
    left: `calc(50% + ${WELCOME_ROOM} / 2)`,
    width: `min(28rem, calc(100% - ${WELCOME_ROOM} - var(--sp-32)))`,
  };
}
