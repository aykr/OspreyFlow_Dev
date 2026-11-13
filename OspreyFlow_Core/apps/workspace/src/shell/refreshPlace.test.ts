// ADR-050 Amendment 3, point 2: the place returned to is the place refreshed, kept in this tab only.
import { describe, expect, it } from "vitest";

import { LAST_GLASS_VIEW_KEY } from "./placeMemory";
import { PLACE_KEY, keepPlace, keptPlace, placeAtLoad, placeOnScreen, restorePlace, type Place } from "./refreshPlace";

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

/** What a refresh does: keep the place on screen, then put it back on the next load. */
function refresh(on: { startChoice: Parameters<typeof placeOnScreen>[0]; view: string }, caseOpen: boolean, tab = memoryStorage()) {
  keepPlace(placeOnScreen(on.startChoice, on.view, caseOpen), tab);
  const place = placeAtLoad({ handedOff: false, addressed: false, caseNamed: false }, tab);
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

describe("what the address says comes first", () => {
  it.each([
    ["a hand-off", { handedOff: true, addressed: false, caseNamed: false }],
    ["an alert's or Rules' address", { handedOff: false, addressed: true, caseNamed: false }],
    ["a case named in the address", { handedOff: false, addressed: false, caseNamed: true }],
  ])("%s wins over the kept place", (_name, load) => {
    const tab = memoryStorage();
    keepPlace("admin", tab);
    expect(placeAtLoad(load, tab)).toBeNull();
  });
});

describe("kept in this tab only", () => {
  it("writes to the storage it is given (the tab's session storage), and nothing else", () => {
    const tab = memoryStorage();
    const other = memoryStorage();
    keepPlace("admin", tab);
    expect(tab.getItem(PLACE_KEY)).toBe("admin");
    expect(keptPlace(other)).toBeNull();
  });

  it("a foreign or unreadable value is ignored", () => {
    const tab = memoryStorage();
    tab.setItem(PLACE_KEY, "somewhere-else");
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
