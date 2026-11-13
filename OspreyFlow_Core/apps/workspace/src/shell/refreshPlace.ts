// `06_DECISIONS.md` ADR-050 Amendment 3, point 2: the place returned to is the place refreshed. Home
// stays Home, a case stays that case (on the Glass view it had, `placeMemory.ts`), and Admin, the
// Studio and Rules and Monitoring stay themselves. Before this a refresh with a case in the tab went
// into the case whatever was on screen, skipping Home (the owner, 13 November 2026, on the demo).
//
// Kept in this tab's `sessionStorage`, as `placeMemory.ts` keeps the Glass's view, and never across
// tabs (never `localStorage`). It is a preference about a screen, not state that matters: unreadable
// or foreign values are ignored, and anything the address says first wins over it — a hand-off from
// the launcher or a case switch (`launcherHandoff.ts`), an alert's or Rules and Monitoring's address
// (`router.ts`), or a case named in the address. It grants nothing: each place is still drawn only
// for whom its rights open it (`startScreen.tsx`, `App.tsx`'s landing checks).
import { KEPT_GLASS_VIEWS, LAST_GLASS_VIEW_KEY } from "./placeMemory";
import type { StartChoice } from "./startScreen";

export const PLACE_KEY = "ospreyflow.place";

export type Place = "home" | "case" | "admin" | "studio" | "rules";
const PLACES: readonly Place[] = ["home", "case", "admin", "studio", "rules"];

/** The place on screen, from `App.tsx`'s own two values: Start's choice and the case's view. */
export function placeOnScreen(startChoice: StartChoice, view: string, caseOpen: boolean): Place {
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
    storage.setItem(PLACE_KEY, place);
  } catch {
    /* a tab that refuses storage refreshes to where the case alone would take it */
  }
}

export function keptPlace(storage: Storage): Place | null {
  try {
    const raw = storage.getItem(PLACE_KEY);
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

function keptGlassView(storage: Storage): string | null {
  try {
    const view = storage.getItem(LAST_GLASS_VIEW_KEY);
    return view && KEPT_GLASS_VIEWS.includes(view) ? view : null;
  } catch {
    return null;
  }
}

export interface LoadAddress {
  /** A hand-off (the launcher's, a case switch's) or its tab, kept over the sign-in round trip. */
  handedOff: boolean;
  /** An alert's or Rules and Monitoring's address is on screen. */
  addressed: boolean;
  /** `?investigation=` names a case. */
  caseNamed: boolean;
}

/** The kept place to put back at load, or `null` when the address says where to go first. */
export function placeAtLoad(load: LoadAddress, storage: Storage): Place | null {
  if (load.handedOff || load.addressed || load.caseNamed) return null;
  return keptPlace(storage);
}
