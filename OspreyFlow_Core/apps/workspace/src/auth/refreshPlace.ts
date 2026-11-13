// `06_DECISIONS.md` ADR-050 Amendment 3, point 2: the place returned to is the place refreshed. Home
// stays Home, a case stays that case (on the Glass view it had, `placeMemory.ts`), and Admin, the
// Studio and Rules and Monitoring stay themselves. Before this a refresh with a case in the tab went
// into the case whatever was on screen, skipping Home (the owner, 13 November 2026, on the demo).
//
// Kept in this tab's `sessionStorage`, as `placeMemory.ts` keeps the Glass's view, and never across
// tabs (never `localStorage`). It is a preference about a screen, not state that matters: unreadable
// or foreign values are ignored, and anything the address says first wins over it, including what was
// noted before a full-page sign-in and is taken back after it: a hand-off from the launcher or a case
// switch (`launcherHandoff.ts`'s stash, which every case switch, alert-in-its-case and Rules-on-a-case
// reload writes), an alert's or Rules and Monitoring's address (`router.ts`, on screen or noted), or a
// case named in the address. It grants nothing: each place is still drawn only for whom its rights
// open it (`startScreen.tsx`, `App.tsx`'s landing checks), the Glass views put back are only those the
// landing check covers, and a place the rights do not offer is kept as Home. Sign out forgets it.
import { handOffPending } from "./launcherHandoff";
import { LAST_GLASS_VIEW_KEY } from "../shell/placeMemory";
import type { PlaceId } from "../shell/places";
import { ADDRESS_NOTE_KEY, parseAddress } from "../shell/router";
import type { StartChoice } from "../shell/startScreen";

export const REFRESH_PLACE_KEY = "ospreyflow.place";

export type Place = "home" | "case" | "admin" | "studio" | "rules";
const PLACES: readonly Place[] = ["home", "case", "admin", "studio", "rules"];

/** The place drawn, from `App.tsx`'s own two values: Start's choice and the case's view. A place
 * chosen that the person's rights (`offered`, `startPlaces`) do not open is drawn as Home
 * (`startScreen.tsx`), so it is kept as Home. */
export function placeOnScreen(
  startChoice: StartChoice,
  view: string,
  caseOpen: boolean,
  offered: readonly PlaceId[],
): Place {
  const chosen: PlaceId | null =
    startChoice === "admin" ? "admin" : startChoice === "ingest" || startChoice === "rules" || startChoice === "glass" ? startChoice : null;
  if (chosen && (chosen === "admin" || !caseOpen) && !offered.includes(chosen)) return "home";
  if (startChoice === "admin") return "admin";
  if (startChoice === "start") return "home";
  if (!caseOpen) {
    // Outside a case, a place chosen on Home is its case list ("Choose the case to load into").
    if (startChoice === "ingest") return "studio";
    if (startChoice === "rules") return "rules";
    if (startChoice === "glass") return "case";
    return "home";
  }
  if (view === "ingest") return "studio";
  if (view === "alerts") return "rules";
  return "case";
}

export function keepPlace(place: Place, storage: Storage): void {
  try {
    storage.setItem(REFRESH_PLACE_KEY, place);
  } catch {
    /* a tab that refuses storage refreshes to where the case alone would take it */
  }
}

/** Sign out: the next person in this tab starts where the address says, not where this one was. */
export function forgetPlace(storage: Storage): void {
  try {
    storage.removeItem(REFRESH_PLACE_KEY);
  } catch {
    /* nothing kept */
  }
}

export function keptPlace(storage: Storage): Place | null {
  try {
    const raw = storage.getItem(REFRESH_PLACE_KEY);
    return PLACES.includes(raw as Place) ? (raw as Place) : null;
  } catch {
    return null;
  }
}

export interface Restored {
  startChoice: StartChoice;
  /** The case's view to open, or `null` for the Glass's own default. */
  view: string | null;
}

/** Start's choice and the case's view that put the kept place back on screen. */
export function restorePlace(place: Place, caseOpen: boolean, storage: Storage): Restored {
  switch (place) {
    case "home":
      return { startChoice: caseOpen ? "start" : null, view: null };
    case "admin":
      return { startChoice: "admin", view: null };
    case "studio":
      return caseOpen ? { startChoice: null, view: "ingest" } : { startChoice: "ingest", view: null };
    case "rules":
      return caseOpen ? { startChoice: null, view: "alerts" } : { startChoice: "rules", view: null };
    case "case":
      return caseOpen ? { startChoice: null, view: keptGlassView(storage) } : { startChoice: "glass", view: null };
  }
}

/** The Glass views put back at load: those `App.tsx`'s landing check corrects for a person whose
 * rights do not open them (ADR-112). The others the Glass keeps (Dashboards, Connection strength,
 * Ownership) are drawn on the view alone, so a refresh opens the Glass's own first view instead. */
const RESTORED_GLASS_VIEWS: readonly string[] = ["graph", "map", "matrix", "reports"];

function keptGlassView(storage: Storage): string | null {
  try {
    const view = storage.getItem(LAST_GLASS_VIEW_KEY);
    return view && RESTORED_GLASS_VIEWS.includes(view) ? view : null;
  } catch {
    return null;
  }
}

/** The kept place to put back at this load, or `null` when the address says where to go first: a
 * hand-off now (`autoSignIn`) or noted over a sign-in round trip (the stash), an alert's or Rules and
 * Monitoring's address on screen or noted, or a case named by `?investigation=`. */
export function placeAtLoad(
  load: { autoSignIn: boolean; pathname: string; search: string },
  storage: Storage,
  now: number = Date.now(),
): Place | null {
  if (load.autoSignIn || handOffPending(storage, now)) return null;
  if (parseAddress(load.pathname).kind !== "none" || notedAddress(storage)) return null;
  if (new URLSearchParams(load.search).has("investigation")) return null;
  return keptPlace(storage);
}

function notedAddress(storage: Storage): boolean {
  try {
    const noted = storage.getItem(ADDRESS_NOTE_KEY);
    return noted !== null && parseAddress(noted).kind !== "none";
  } catch {
    return false;
  }
}
