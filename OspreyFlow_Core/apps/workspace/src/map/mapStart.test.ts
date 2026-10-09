// Where the map opens (8 October 2026). With nothing on the canvas that has a map position (the HMP
// case's locations are on a site plan, not the map), the graph layer had no extent to fit and the
// camera was fitted to an undefined box: the map drew black, with no word of why.
import { describe, expect, it } from "vitest";

import { mapStart } from "./mapStart";

const GREAT_BRITAIN = { centerLon: -6.41, centerLat: 55.73, centerZoom: 5 };

describe("mapStart", () => {
  it("fits the nodes when any has a map position", () => {
    expect(mapStart(3, GREAT_BRITAIN)).toEqual({ kind: "fit" });
  });

  it("opens on the basemap's own centre when none has", () => {
    expect(mapStart(0, GREAT_BRITAIN)).toEqual({ kind: "view", center: [-6.41, 55.73], zoom: 5 });
  });

  it("opens on the whole world when the basemap says nothing of where it is", () => {
    expect(mapStart(0, null)).toEqual({ kind: "view", center: [0, 0], zoom: 1 });
  });
});
