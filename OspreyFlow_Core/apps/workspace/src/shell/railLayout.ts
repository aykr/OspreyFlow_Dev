// The Glass's left rail as ADR-145 Amendment 12 lays it out (amending Amendment 2's variant B): which
// places stand on the rail itself, in what order, and which are one click away under its ⋯ Explore
// Details, in what order, with the names people see. `App.tsx` draws it from these, and the keyboard
// harnesses read the same lists, so a change here is what their cases see. Which entries a person sees
// at all is `rights/visibility.ts`'s `railEntries`, unchanged.
import type { RailEntry } from "../rights/visibility";

/** On the rail itself, in this order. */
export const ON_THE_RAIL: readonly RailEntry[] = ["cases", "explore", "questions", "dashboards"];
/** Under ⋯ Explore Details, in this order. */
export const EXPLORE_DETAILS: readonly RailEntry[] = ["history", "ownership", "strength"];

/** The names people see: *Questions* is *Ask & Chat* (Amendment 12). */
export const RAIL_LABELS: Record<RailEntry, string> = {
  cases: "Cases",
  explore: "Explore",
  questions: "Ask & Chat",
  dashboards: "Dashboards",
  history: "History",
  ownership: "Ownership",
  strength: "Connection strength",
};

/** `entries` split between the rail and its menu, each in its own order; any entry in neither list is
 * left out. */
export function splitRail<T extends { id: string }>(entries: readonly T[]): { items: T[]; more: T[] } {
  const inOrder = (order: readonly string[]) =>
    order.flatMap((id) => entries.filter((entry) => entry.id === id));
  return { items: inOrder(ON_THE_RAIL), more: inOrder(EXPLORE_DETAILS) };
}

/** The rail's entries that open a panel over the place (a drawer), not a place of their own (ADR-145
 * Amendment 14 decision 3). */
export const PANEL_OPENERS: readonly RailEntry[] = ["cases", "explore", "questions", "history"];

/** How the rail marks an entry, one place, one marker (Amendment 14 decision 3): a place is pressed while it is
 * the view open; a panel's opener is never pressed, only expanded while its panel is open. `App.tsx` and the
 * places harness both read it, so the harness cannot agree with a copy. */
export function railMark(
  id: RailEntry,
  state: { view: string; open: ReadonlySet<RailEntry> },
): { pressed: boolean } | { expanded: boolean } {
  return PANEL_OPENERS.includes(id) ? { expanded: state.open.has(id) } : { pressed: state.view === id };
}
