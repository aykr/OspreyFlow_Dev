// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  entityPictureFor,
  forgetEntityPictures,
  loadEntityPictures,
  onEntityPicturesChange,
  removeEntityPicture,
  setEntityPictureForTest,
} from "./entityPictures";
import { forgetIconChoicesForTest, resolveIconForNode, setIconChoice } from "./iconChoices";

vi.mock("./iconImage", () => ({
  thumbnailFromFile: vi.fn(async () => "data:image/png;base64,T0hVTUI="),
}));

// ADR-105. An entity may have a picture of its own, held in the case as evidence; it is drawn in
// that node before the analyst's picture for its type (ADR-079), which is drawn before the
// ontology's icon.

const OWN = "data:image/png;base64,T1dO";
const TYPE = "data:image/png;base64,VFlQRQ==";
const FILL = "#1b2a6b";
const API = { apiBaseUrl: "http://api", bearerToken: "t", investigationId: "inv-1" };

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
  forgetEntityPictures();
});
afterEach(() => vi.unstubAllGlobals());

describe("what a node is drawn with", () => {
  it("is the entity's own picture first, for that entity only", () => {
    setIconChoice("Vehicle", { kind: "image", dataUrl: TYPE });
    setEntityPictureForTest("car-1", OWN);
    expect(resolveIconForNode("car-1", "Vehicle", "vehicle", FILL)).toMatchObject({ kind: "image", dataUrl: OWN });
    expect(resolveIconForNode("car-2", "Vehicle", "vehicle", FILL)).toMatchObject({ kind: "image", dataUrl: TYPE });
  });

  it("is the type's picture, then the ontology's icon, when the entity has none", () => {
    expect(resolveIconForNode("car-2", "Vehicle", "vehicle", FILL)).toMatchObject({ kind: "glyph", name: "vehicle" });
  });

  it("is keyed by the node, so two entities with the same picture are drawn apart", () => {
    setEntityPictureForTest("car-1", OWN);
    setEntityPictureForTest("car-2", OWN);
    const one = resolveIconForNode("car-1", "Vehicle", "vehicle", FILL);
    const two = resolveIconForNode("car-2", "Vehicle", "vehicle", FILL);
    expect(one?.kind === "image" && two?.kind === "image" && one.key !== two.key).toBe(true);
  });

  it("never draws a picture that is not a small raster data address", () => {
    setEntityPictureForTest("car-1", "data:image/svg+xml;base64,PHN2Zz4=");
    expect(resolveIconForNode("car-1", "Vehicle", "vehicle", FILL)).toMatchObject({ kind: "glyph" });
  });
});

function server(answer: { node_id: string; document_id: string }[]) {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET" });
      if (url.endsWith("/pictures")) return new Response(JSON.stringify(answer), { status: 200 });
      if (init?.method === "DELETE") return new Response("{}", { status: 200 });
      // A plain body with its type, not `new Blob(...)`: under jsdom that is jsdom's Blob, which
      // Node 22's own `Response` cannot read (it calls `blob.stream()`), so the picture was lost.
      return new Response("png", { status: 200, headers: { "Content-Type": "image/png" } });
    }),
  );
  return calls;
}

describe("loading the pictures in view", () => {
  it("fetches the picture of each entity the server answers for, and tells the canvas", async () => {
    const calls = server([{ node_id: "car-1", document_id: "content:1" }]);
    const told = vi.fn();
    onEntityPicturesChange(told);
    await loadEntityPictures(API, ["car-1", "car-2"]);
    expect(entityPictureFor("car-1")).toBe("data:image/png;base64,T0hVTUI=");
    expect(entityPictureFor("car-2")).toBeUndefined();
    expect(calls.map((c) => c.url)).toEqual([
      "http://api/v1/investigations/inv-1/pictures",
      "http://api/v1/investigations/inv-1/nodes/car-1/picture",
    ]);
    expect(told).toHaveBeenCalledTimes(1);
  });

  it("does not fetch a picture already held, and drops one the server no longer answers for", async () => {
    server([{ node_id: "car-1", document_id: "content:1" }]);
    await loadEntityPictures(API, ["car-1"]);
    const calls = server([{ node_id: "car-1", document_id: "content:1" }]);
    await loadEntityPictures(API, ["car-1"]);
    expect(calls).toHaveLength(1);
    server([]);
    await loadEntityPictures(API, ["car-1"]);
    expect(entityPictureFor("car-1")).toBeUndefined();
  });

  it("removing a picture asks the server and draws the type's again", async () => {
    setEntityPictureForTest("car-1", OWN);
    const calls = server([]);
    await removeEntityPicture(API, "car-1");
    expect(calls).toEqual([{ url: "http://api/v1/investigations/inv-1/nodes/car-1/picture", method: "DELETE" }]);
    expect(entityPictureFor("car-1")).toBeUndefined();
  });
});
