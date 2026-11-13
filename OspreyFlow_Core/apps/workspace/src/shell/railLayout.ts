// The Glass's left rail and its views as ADR-145 Amendment 15 lays them out (the owner's navigation decision of
// 13 November 2026, amending Amendments 2 and 12): the panel openers on the rail, in what order, how each is
// marked, and the top bar's one view switch and its More views, with the names people see. `App.tsx` draws it from these, and the keyboard
// harnesses read the same lists, so a change here is what their cases see. Which entries a person sees
// at all is `rights/visibility.ts`'s `railEntries`, unchanged.
import type { RailEntry } from "../rights/visibility";

/** On the rail itself, in this order: the panel openers alone (the owner's navigation decision of 13 November 2026,
 * ADR-145 Amendment 15). Cases is reached from the case line (its switcher's *All cases*, and *Views in this case*);
 * Dashboards (now *Reports*), Ownership and Connection strength are views in the top bar's view switch. */
export const ON_THE_RAIL: readonly RailEntry[] = ["explore", "questions", "history"];
/** Under ⋯ Explore Details: none since Amendment 15, so the rail draws no Explore Details. */
export const EXPLORE_DETAILS: readonly RailEntry[] = [];

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

/** The rail's entries, each of which opens a panel over the view (a drawer), never a view (ADR-145 Amendments 14
 * and 15). */
export const PANEL_OPENERS: readonly RailEntry[] = ["explore", "questions", "history"];

/** How the rail marks an entry, one place, one marker (Amendment 14 decision 3): a place is pressed while it is
 * the view open; a panel's opener is never pressed, only expanded while its panel is open. `App.tsx` and the
 * places harness both read it, so the harness cannot agree with a copy. */
export function railMark(
  id: RailEntry,
  state: { view: string; open: ReadonlySet<RailEntry> },
): { pressed: boolean } | { expanded: boolean } {
  return PANEL_OPENERS.includes(id) ? { expanded: state.open.has(id) } : { pressed: state.view === id };
}

/** The Glass's views (the owner's navigation decision of 13 November 2026, ADR-145 Amendment 15): the top bar's one
 * view switch, in this order, then its More views, in this order. *Reports* is ADR-111 Amendment 3's dashboards view
 * (id `dashboards`), unchanged inside; *Figures* is ADR-145 Amendment 4 decision 8's (id `reports`). `App.tsx` and the
 * keyboard harnesses read these, so a harness cannot keep an older switch. */
export const VIEW_SWITCH = ["graph", "map", "boards", "dashboards"] as const;
export const MORE_VIEWS = ["matrix", "reports", "ownership", "strength"] as const;
export type SwitchView = (typeof VIEW_SWITCH)[number] | (typeof MORE_VIEWS)[number];
export const VIEW_LABELS: Record<SwitchView, string> = {
  graph: "Graph",
  map: "Map",
  boards: "Drawing board",
  dashboards: "Reports",
  matrix: "Matrix",
  reports: "Figures",
  ownership: "Ownership",
  strength: "Connection strength",
};

/** The views offered, split between the switch and More views, each in its order. Someone offered none of the
 * switch's (a Reports Viewer offered Figures alone) has theirs in the switch itself. */
export function splitViews<T extends { id: string }>(offered: readonly T[]): { main: T[]; more: T[] } {
  const inOrder = (order: readonly string[]) => order.flatMap((id) => offered.filter((v) => v.id === id));
  const main = inOrder(VIEW_SWITCH);
  const more = inOrder(MORE_VIEWS);
  return main.length > 0 ? { main, more } : { main: more, more: [] };
}
