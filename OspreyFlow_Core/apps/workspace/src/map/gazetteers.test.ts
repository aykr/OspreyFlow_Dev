// The case's gazetteers (`gazetteers.ts`, P6; ADR-147 Amendment 2, the owner's ruling 6): the routes
// it asks, the three empty cases it tells apart, and its words for a refusal, never the Conduit's.
import { describe, expect, it } from "vitest";

import { GazetteersFailed, addGazetteer, caseGazetteers, removeGazetteer } from "./gazetteers";

type Answer = { status: number; body: unknown };

/** A fetch that answers by URL and method, and records what was asked. */
function conduit(routes: Record<string, Answer>, asked: Request[] = []): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(String(input), init);
    asked.push(request);
    const answer = routes[`${request.method} ${request.url}`];
    if (answer === undefined) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(answer.body), { status: answer.status });
  }) as typeof fetch;
}

const GAZ = "http://conduit/v1/investigations/case%2F1/map/gazetteers";
const DATASETS = "http://conduit/v1/investigations/case%2F1/datasets";
const OSM = { dataset_id: "gazetteer-osm-uk", name: "OpenStreetMap places (UK)", added: false };

describe("caseGazetteers", () => {
  it("asks the case's gazetteers and the dataset it reads, with the token, and is ready", async () => {
    const asked: Request[] = [];
    const state = await caseGazetteers(
      "http://conduit",
      "t0k",
      "case/1",
      conduit(
        {
          [`GET ${GAZ}`]: { status: 200, body: { gazetteers: [OSM], said: null } },
          [`GET ${DATASETS}`]: {
            status: 200,
            body: [{ id: "ds-1", name: "Operation Kestrel", owning_unit: "unit-1", kind: "source" }],
          },
        },
        asked,
      ),
    );
    expect(state).toEqual({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] });
    expect(asked.map((r) => `${r.method} ${r.url}`).sort()).toEqual([`GET ${DATASETS}`, `GET ${GAZ}`]);
    expect(asked.every((r) => r.headers.get("Authorization") === "Bearer t0k")).toBe(true);
  });

  it.each([
    ["reads nothing", [], "reads_nothing"],
    [
      "reads more than one dataset",
      [
        { id: "a", name: "A", owning_unit: "u", kind: "source" },
        { id: "b", name: "B", owning_unit: "u", kind: "source" },
      ],
      "not_one_source",
    ],
    ["reads a composite", [{ id: "c", name: "C", owning_unit: "u", kind: "composite" }], "not_one_source"],
  ])("tells a case that %s from one with no gazetteer built", async (_why, datasets, expected) => {
    const state = await caseGazetteers(
      "http://conduit",
      "t",
      "case/1",
      conduit({
        [`GET ${GAZ}`]: { status: 200, body: { gazetteers: [] } },
        [`GET ${DATASETS}`]: { status: 200, body: datasets },
      }),
    );
    expect(state).toEqual({ state: expected });
  });

  it("says none is built when the case reads one source dataset and its unit has none", async () => {
    const state = await caseGazetteers(
      "http://conduit",
      "t",
      "case/1",
      conduit({
        [`GET ${GAZ}`]: { status: 200, body: { gazetteers: [] } },
        [`GET ${DATASETS}`]: { status: 200, body: [{ id: "ds-1", name: "N", owning_unit: "u", kind: "source" }] },
      }),
    );
    expect(state).toEqual({ state: "none_built" });
  });

  it("says a refusal in its own words", async () => {
    const refused = conduit({
      [`GET ${GAZ}`]: { status: 403, body: { detail: "internal words" } },
      [`GET ${DATASETS}`]: { status: 200, body: [] },
    });
    await expect(caseGazetteers("http://conduit", "t", "case/1", refused)).rejects.toThrow(
      new GazetteersFailed("You may not see this case's gazetteers."),
    );
  });
});

describe("addGazetteer and removeGazetteer", () => {
  const ROUTE = "http://conduit/v1/datasets/ds%2F1/gazetteers/gazetteer-osm-uk";

  it("put and delete the dataset's gazetteer, with no body, and return the Conduit's answer", async () => {
    const asked: Request[] = [];
    const added = { gazetteers: [{ ...OSM, added: true }], said: null };
    const removed = { gazetteers: [OSM], said: "The gazetteer is removed: its places stay." };
    const fetchImpl = conduit(
      { [`PUT ${ROUTE}`]: { status: 200, body: added }, [`DELETE ${ROUTE}`]: { status: 200, body: removed } },
      asked,
    );
    expect(await addGazetteer("http://conduit", "t0k", "ds/1", "gazetteer-osm-uk", fetchImpl)).toEqual(added);
    expect(await removeGazetteer("http://conduit", "t0k", "ds/1", "gazetteer-osm-uk", fetchImpl)).toEqual(removed);
    expect(asked.map((r) => r.method)).toEqual(["PUT", "DELETE"]);
    expect(asked.every((r) => r.headers.get("Authorization") === "Bearer t0k")).toBe(true);
    expect(await asked[0]!.text()).toBe("");
  });

  it.each([
    [403, "You may not change this dataset's gazetteers: it needs the right to run pipelines."],
    [404, "There is no gazetteer of that name for this case's dataset's unit."],
    [409, "This case's dataset takes no gazetteer: it is a composite or a drawing."],
    [500, "The gazetteer could not be changed (HTTP 500). Try again."],
  ])("says a %i in its own words, never the Conduit's", async (status, words) => {
    const fetchImpl = conduit({ [`PUT ${ROUTE}`]: { status, body: { detail: "internal words" } } });
    await expect(addGazetteer("http://conduit", "t", "ds/1", "gazetteer-osm-uk", fetchImpl)).rejects.toThrow(
      new GazetteersFailed(words),
    );
  });

  it("says an unreachable Conduit in its own words", async () => {
    const unreachable = (async () => {
      throw new TypeError("network down at 10.0.0.1");
    }) as typeof fetch;
    await expect(removeGazetteer("http://conduit", "t", "ds", "g", unreachable)).rejects.toThrow(
      "The gazetteers could not reach the Conduit. Try again.",
    );
  });
});
