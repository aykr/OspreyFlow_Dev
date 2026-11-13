// ADR-050 Amendment 3, point 3: the place returned to is the place refreshed, kept in this tab only,
// giving way to whatever the address says or noted over a sign-in round trip, and granting nothing.
import { describe, expect, it } from "vitest";

import { HANDOFF_STORAGE_KEY } from "./launcherHandoff";
import { LAST_GLASS_VIEW_KEY } from "../shell/placeMemory";
import type { PlaceId } from "../shell/places";
import { ADDRESS_NOTE_KEY } from "../shell/router";
import { REFRESH_PLACE_KEY, forgetPlace, keepPlace, keptPlace, placeAtLoad, placeOnScreen, restorePlace, type Place } from "./refreshPlace";

const NOW = 1_800_000_000_000;
const EVERY_PLACE: PlaceId[] = ["glass", "ingest", "rules", "admin"];
const PLAIN_LOAD = { autoSignIn: false, pathname: "/", search: "" };

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k) => map.get(k) ?? null,
    key: (i) => Array.from(map.keys())[i] ?? null,
    removeItem: (k) => void map.delete(k),
    setItem: (k, v) => void map.set(k, v),
  };
}

/** What a refresh does: keep the place drawn, then put it back on the next load. */
function refresh(
  on: { startChoice: Parameters<typeof placeOnScreen>[0]; view: string },
  caseOpen: boolean,
  tab = memoryStorage(),
  offered: PlaceId[] = EVERY_PLACE,
) {
  keepPlace(placeOnScreen(on.startChoice, on.view, caseOpen, offered), tab);
  const place = placeAtLoad(PLAIN_LOAD, tab, NOW);
  return place ? restorePlace(place, caseOpen, tab) : null;
}

describe("a refresh returns to the place refreshed", () => {
  it("Home stays Home, with a case in the tab (before this it went into the case)", () => {
    expect(refresh({ startChoice: "start", view: "graph" }, true)).toEqual({ startChoice: "start", view: null });
  });

  it("Home stays Home with no case", () => {
    expect(refresh({ startChoice: null, view: "graph" }, false)).toEqual({ startChoice: null, view: null });
  });

  it("a case stays that case, on the Glass view it had", () => {
    const tab = memoryStorage();
    tab.setItem(LAST_GLASS_VIEW_KEY, "map");
    expect(refresh({ startChoice: null, view: "map" }, true, tab)).toEqual({ startChoice: null, view: "map" });
  });

  it("Admin stays Admin, with a case or without", () => {
    expect(refresh({ startChoice: "admin", view: "graph" }, true)).toEqual({ startChoice: "admin", view: null });
    expect(refresh({ startChoice: "admin", view: "graph" }, false)).toEqual({ startChoice: "admin", view: null });
  });

  it("the Studio stays the Studio", () => {
    expect(refresh({ startChoice: null, view: "ingest" }, true)).toEqual({ startChoice: null, view: "ingest" });
    expect(refresh({ startChoice: "ingest", view: "graph" }, false)).toEqual({ startChoice: "ingest", view: null });
  });

  it("Rules and Monitoring stays itself", () => {
    expect(refresh({ startChoice: null, view: "alerts" }, true)).toEqual({ startChoice: null, view: "alerts" });
    expect(refresh({ startChoice: "rules", view: "graph" }, false)).toEqual({ startChoice: "rules", view: null });
  });
});

describe("what the address says, now or noted over a sign-in, comes first", () => {
  it("a hand-off arriving now", () => {
    const tab = memoryStorage();
    keepPlace("home", tab);
    expect(placeAtLoad({ ...PLAIN_LOAD, autoSignIn: true }, tab, NOW)).toBeNull();
  });

  it("a case switch carried over the identity provider's round trip, whose stash names no tab", () => {
    // `caseUrl(id)` stashes `{ view: null }`; the page that comes back with `?code=` has no `from`.
    const tab = memoryStorage();
    keepPlace("home", tab);
    tab.setItem(HANDOFF_STORAGE_KEY, JSON.stringify({ view: null, at: NOW - 5_000 }));
    expect(placeAtLoad(PLAIN_LOAD, tab, NOW)).toBeNull();
  });

  it("a stale stash (a sign-in nobody finished) no longer counts", () => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    tab.setItem(HANDOFF_STORAGE_KEY, JSON.stringify({ view: null, at: NOW - 11 * 60 * 1000 }));
    expect(placeAtLoad(PLAIN_LOAD, tab, NOW)).toBe("admin");
  });

  it.each(["/rules", "/alerts/a1"])("an address on screen (%s)", (pathname) => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    expect(placeAtLoad({ ...PLAIN_LOAD, pathname }, tab, NOW)).toBeNull();
  });

  it.each(["/rules", "/alerts/a1"])("an address noted before a full-page sign-in (%s), back at the root", (noted) => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    tab.setItem(ADDRESS_NOTE_KEY, noted);
    expect(placeAtLoad(PLAIN_LOAD, tab, NOW)).toBeNull();
    // Read, not taken: the bootstrap still takes it back after the sign-in.
    expect(tab.getItem(ADDRESS_NOTE_KEY)).toBe(noted);
  });

  it("a case named by ?investigation=", () => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    expect(placeAtLoad({ ...PLAIN_LOAD, search: "?investigation=c1" }, tab, NOW)).toBeNull();
  });
});

describe("it grants nothing", () => {
  it("a place the rights do not offer is kept as Home, as it is drawn", () => {
    expect(placeOnScreen("admin", "graph", true, ["glass"])).toBe("home");
    expect(placeOnScreen("ingest", "graph", false, ["glass"])).toBe("home");
    expect(placeOnScreen("rules", "graph", false, ["glass", "ingest"])).toBe("home");
  });

  it.each(["dashboards", "strength", "ownership"])(
    "a Glass view drawn without a rights check (%s) is not put back; the Glass opens its own first view",
    (view) => {
      const tab = memoryStorage();
      tab.setItem(LAST_GLASS_VIEW_KEY, view);
      expect(restorePlace("case", true, tab)).toEqual({ startChoice: null, view: null });
    },
  );

  it("sign out forgets the place, so the next person in the tab starts where the address says", () => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    forgetPlace(tab);
    expect(placeAtLoad(PLAIN_LOAD, tab, NOW)).toBeNull();
  });
});

describe("kept in this tab only", () => {
  it("writes to the storage it is given (the tab's session storage), and nothing else", () => {
    const tab = memoryStorage();
    const other = memoryStorage();
    keepPlace("admin", tab);
    expect(tab.getItem(REFRESH_PLACE_KEY)).toBe("admin");
    expect(keptPlace(other)).toBeNull();
  });

  it("a foreign or unreadable value is ignored", () => {
    const tab = memoryStorage();
    tab.setItem(REFRESH_PLACE_KEY, "somewhere-else");
    expect(keptPlace(tab)).toBeNull();
    const refusing = { ...memoryStorage(), getItem: () => { throw new Error("denied"); } } as Storage;
    expect(keptPlace(refusing)).toBeNull();
  });

  it("every place round-trips", () => {
    for (const place of ["home", "case", "admin", "studio", "rules"] as Place[]) {
      const tab = memoryStorage();
      keepPlace(place, tab);
      expect(keptPlace(tab)).toBe(place);
    }
  });
});
