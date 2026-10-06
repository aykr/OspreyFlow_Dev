// What the right-click menu on a link offers (ADR-080). Kept apart from the canvas so the choice of
// entries can be tested without a renderer. The canvas supplies what each entry does.
import type { Edge } from "../../../../packages/schemas/generated";
import type { RadialMenuItem } from "../design/primitives/RadialMenu";

export const SAME_AS = "SAME_AS";
export const NOT_SAME_AS = "NOT_SAME_AS";

export interface LinkMenuActions {
  onCollapse: () => void;
  onExpand: () => void;
  onConfirm: () => void;
  onNotSame: () => void;
  onExplain: () => void;
  onNote: () => void;
  onHide: () => void;
  onChange: () => void;
  onHistory: () => void;
  /** ADR-089: the events behind the link (the emails between two addresses). Offered on any link
   * other than the resolution engine's when `eventsLabel` is given. */
  onEvents?: () => void;
  eventsLabel?: string;
  /** Owner, 6 October 2026: the link's emails or messages written onto the canvas as Documents, as
   * an entry of its own (ADR-092 decisions 1 and 2), offered with `eventsToCanvasLabel`. */
  onEventsToCanvas?: () => void;
  eventsToCanvasLabel?: string;
}

/** "Same as: Person: Ada ↔ Person: A. Lovelace" — which link this menu belongs to; the caller passes the type's display name (ADR-091). */
export function linkMenuTitle(type: string, sourceLabel: string, targetLabel: string): string {
  return `${type}: ${sourceLabel} ↔ ${targetLabel}`;
}

function entry(
  id: string,
  label: string,
  group: string,
  onSelect: () => void,
): RadialMenuItem {
  return { id, label, group, count: undefined, onSelect };
}

/**
 * The entries for `edge`, in the order they are listed and reached by keyboard.
 *
 * - **Same-as** (the engine's own "these are one entity"): fold the nodes into one in the view and
 *   open them again, confirm or refute the match, explain how it scored, note it, hide it.
 * - **Not-the-same**: a note and hiding only. It is a judgement the analyst made; undoing it is a
 *   new judgement, not an edit.
 * - **Any other link**: change it (type and details, with a reason), see how it came to be as it
 *   is, note it, hide it.
 *
 * `folded` says whether the same-as nodes are folded now, which turns *Collapse* into *Expand*.
 */
export function linkMenuItems(edge: Edge, folded: boolean, a: LinkMenuActions): RadialMenuItem[] {
  if (edge.type === SAME_AS) {
    return [
      folded
        ? entry("link-expand", "Expand", "This match", a.onExpand)
        : entry("link-collapse", "Collapse into one node", "This match", a.onCollapse),
      entry("link-confirm", "Confirm as the same", "This match", a.onConfirm),
      entry("link-not-same", "Mark as not the same", "This match", a.onNotSame),
      entry("link-explain", "Explain this link", "This match", a.onExplain),
      entry("link-note", "Add a note", "Notes and view", a.onNote),
      entry("link-hide", "Hide link", "Notes and view", a.onHide),
    ];
  }
  if (edge.type === NOT_SAME_AS) {
    return [
      entry("link-note", "Add a note", "Notes and view", a.onNote),
      entry("link-hide", "Hide link", "Notes and view", a.onHide),
    ];
  }
  return [
    ...(a.onEvents && a.eventsLabel
      ? [entry("link-events", a.eventsLabel, "This link", a.onEvents)]
      : []),
    ...(a.onEventsToCanvas && a.eventsToCanvasLabel
      ? [entry("link-events-canvas", a.eventsToCanvasLabel, "This link", a.onEventsToCanvas)]
      : []),
    entry("link-change", "Change link…", "This link", a.onChange),
    entry("link-history", "Show change history", "This link", a.onHistory),
    entry("link-note", "Add a note", "Notes and view", a.onNote),
    entry("link-hide", "Hide link", "Notes and view", a.onHide),
  ];
}
