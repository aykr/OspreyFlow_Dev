// The Glass's left rail and its views as ADR-145 Amendment 15 lays them out (the owner's navigation decision of
// 13 November 2026, amending Amendments 2 and 12): the panel openers on the rail, in what order, how each is
// marked, and the top bar's one view switch and its More views, with the names people see. `App.tsx` draws it from these, and the keyboard
// harnesses read the same lists, so a change here is what their cases see. Which entries a person sees
// at all is `rights/visibility.ts`'s `railEntries`, unchanged.
import { landingView, railEntries, viewsFor, type RailEntry, type Rights } from "../rights/visibility";

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

/** How the rail marks an entry (Amendment 15): a panel's opener is never pressed, only expanded while its panel is
 * open. Since Amendment 15 every entry on the rail is a panel's opener, so its `pressed` answer serves only an entry
 * outside PANEL_OPENERS, of which there is none today. `App.tsx` and the places harness both read it. */
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
 * switch's (the built-in Administrator, offered Connection strength alone) has theirs in the switch itself. */
export function splitViews<T extends { id: string }>(offered: readonly T[]): { main: T[]; more: T[] } {
  const inOrder = (order: readonly string[]) => order.flatMap((id) => offered.filter((v) => v.id === id));
  const main = inOrder(VIEW_SWITCH);
  const more = inOrder(MORE_VIEWS);
  return main.length > 0 ? { main, more } : { main: more, more: [] };
}

/** What leaves the top bar first when it runs out of room on one line (the owner's ruling of 14 November 2026, spec 02
 * §3): the bar stays one line high, and the least-used go first. *Build a report* (a link out of the Glass) folds into
 * More views first; then the views, Reports, the Drawing board, the Map and a node's Messages, each into More views; then
 * the place switcher into one menu naming the place open; Graph, the Glass's landing view, last of all. A view in the
 * switch this list does not name (the built-in Administrator's Connection strength) folds just before Graph. Every one
 * folded is still one click away under More views (or the places menu), and by keyboard. `TopBar` reads this; it
 * measures, folds one more while any item sits on a second line, and starts again from none folded when the bar's
 * width changes. */
export const BAR_FOLD_ORDER = ["build-a-report", "dashboards", "boards", "map", "dossier", "places", "graph"] as const;

/** The views this person is offered, in the switch's order then More views': each by the rights that offered it
 * before Amendment 15 (`viewsFor`, `railEntries`), the drawing board by `investigate` as its routes ask (offered with
 * the graph). `App.tsx` and the keyboard harnesses read this one list, so a harness cannot offer what the App would
 * not. While the rights are unknown (`null`) it offers what the Glass always offered (ADR-112). */
export function offeredViews(rights: Rights): SwitchView[] {
  const views = viewsFor(rights);
  const offered = new Set<string>([...views, ...railEntries(rights), ...(views.includes("graph") ? ["boards"] : [])]);
  return [...VIEW_SWITCH, ...MORE_VIEWS].filter((id) => offered.has(id));
}

/** The view to give way to when the one open is not offered (exactly one view current, Amendment 15): the Glass's
 * landing view (`landingView`) where it is offered, else the first offered (the built-in Administrator's Connection
 * strength), else the landing view. */
export function viewToLandOn(rights: Rights): string {
  const offered: readonly string[] = offeredViews(rights);
  const landing = landingView(rights);
  return offered.includes(landing) ? landing : (offered[0] ?? landing);
}
