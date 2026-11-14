// What can be done to the whole selection, said once (ADR-078 Amendment 1, the owner's Part C of
// 13 November 2026): the bottom bar and the canvas's right-click menu both read these words and this
// order, so a right-click offers the same actions, in the same words, as the bar.
import type { RadialMenuItem } from "../design/primitives";
import { degreeShown, type SelectionBarProps } from "./SelectionBar";

export const SELECTION_WORDS = {
  undoLit: "Undo select what is lit",
  expand: "Expand",
  linksAmong: "Show links",
  ask: "Ask the model about these…",
  saveView: "Save as a view",
  remove: "Remove from view",
  clear: "Clear",
} as const;

/** The menu ids of the selection's actions. `save-selected-as-view` keeps ADR-144 decision 4's id. */
export const SELECTION_ITEM_IDS = {
  undoLit: "selection-undo-lit",
  expand: "selection-expand",
  linksAmong: "selection-links-among",
  ask: "selection-ask",
  saveView: "save-selected-as-view",
  remove: "selection-remove",
  clear: "selection-clear",
} as const;

/** The bar's actions as menu entries, in the bar's order and on the bar's conditions: an action the bar
 * does not offer (its handler absent, or *Show links* for one node) is not in the menu either. *Show
 * links* from the menu looks as far as the bar's stepper reads (`degree`, held by the canvas). */
export function selectionMenuItems(bar: SelectionBarProps): RadialMenuItem[] {
  if (bar.count === 0) return [];
  const items: RadialMenuItem[] = [];
  const add = (key: keyof typeof SELECTION_WORDS, onSelect: (() => void) | undefined) => {
    if (onSelect) items.push({ id: SELECTION_ITEM_IDS[key], label: SELECTION_WORDS[key], count: undefined, onSelect });
  };
  add("undoLit", bar.litNote ? bar.onUndoLit : undefined);
  add("expand", bar.onExpand);
  const linksAmong = bar.onLinksAmong;
  add("linksAmong", linksAmong && bar.count > 1 ? () => linksAmong(degreeShown(bar.count, bar.degree ?? 1)) : undefined);
  add("ask", bar.onAsk); // offered whatever is selected, as the bar (ADR-098 Amendment 7: a question needs no Document)
  add("saveView", bar.onSaveView);
  add("remove", bar.onRemove);
  add("clear", bar.onClear);
  return items;
}
