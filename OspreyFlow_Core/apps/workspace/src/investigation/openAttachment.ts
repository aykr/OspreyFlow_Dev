// Where an attachment of the case brief opens (ADR-128 decision 3). A canvas view is a case, a tab, so
// it opens as one; a saved trend is on the Reports view's Trends tab; a saved pattern is in the Query
// builder panel and an assessment in the Inspector panel, both beside the canvas. The place is where
// the thing is worked with: the Glass has no deeper link to one trend, pattern or judgement, and the
// brief does not invent one.
import type { AttachmentKind } from "./briefApi";

export type SidePanelName = "query-builder" | "inspector";

export type AttachmentPlace =
  | { place: "case"; id: string }
  | { place: "reports"; tab: "trends" }
  | { place: "panel"; panel: SidePanelName };

export function placeOf(kind: AttachmentKind, id: string): AttachmentPlace {
  switch (kind) {
    case "view":
      return { place: "case", id };
    case "trend":
      return { place: "reports", tab: "trends" };
    case "pattern":
      return { place: "panel", panel: "query-builder" };
    case "assessment":
      return { place: "panel", panel: "inspector" };
  }
}

/** Unfolds the named side panel if it is folded and puts focus on its header, the control a keyboard
 * person works the panel from (`SidePanelStack`). False when the panel is not on the page (a view
 * with no side panels), in which case nothing is touched. */
export function revealPanel(panel: SidePanelName, root: ParentNode = document): boolean {
  const toggle = root.querySelector<HTMLElement>(`[data-panel-slot="${panel}"] .side-panel-header__toggle`);
  if (!toggle) return false;
  if (toggle.getAttribute("aria-expanded") === "false") toggle.click();
  toggle.focus();
  return true;
}
