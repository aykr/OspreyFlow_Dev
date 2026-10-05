import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LinkTypeError,
  fetchCaseLinkTypes,
  listProposals,
  promoteProposal,
  proposeLinkType,
  rejectProposal,
  retireLinkType,
  withdrawProposal,
} from "./linkTypesApi";

afterEach(() => vi.unstubAllGlobals());

const BASE = "http://api.test";

function stub(status: number, json: unknown) {
  const fetchMock = vi.fn(async () => ({ ok: status >= 200 && status < 300, status, json: async () => json }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function call(fetchMock: ReturnType<typeof stub>, n = 0): [string, RequestInit] {
  return fetchMock.mock.calls[n] as unknown as [string, RequestInit];
}

const KNOWN_TO = { name: "KNOWN_TO", from: ["Person"], to: ["Person"], basis: "probabilistic", analyst_defined: true };

describe("the case's link types", () => {
  it("reads the case's own list, marking the proposed ones", async () => {
    const fetchMock = stub(200, { types: [{ definition: KNOWN_TO, proposal_id: "p1" }, { definition: { name: "USES" }, proposal_id: null }] });
    const got = await fetchCaseLinkTypes(BASE, "tok", "inv 1");
    expect(call(fetchMock)[0]).toBe(`${BASE}/v1/investigations/inv%201/link-types`);
    expect(got.definitions.map((t) => t.name)).toEqual(["KNOWN_TO", "USES"]);
    expect([...got.proposed]).toEqual(["KNOWN_TO"]);
  });

  it("treats an answer that is not a list as a failure, not as no types", async () => {
    stub(200, { nope: true });
    await expect(fetchCaseLinkTypes(BASE, "tok", "inv-1")).rejects.toBeInstanceOf(LinkTypeError);
  });
});

describe("proposing and withdrawing", () => {
  it("posts the proposal to the case and returns it", async () => {
    const fetchMock = stub(200, { id: "p1", name: "KNOWN_TO", status: "pending" });
    const input = { name: "KNOWN_TO", from_types: ["Person"], to_types: ["Person"], directed: false, reason: "By sight" };
    const got = await proposeLinkType(BASE, "tok", "inv-1", input);
    expect(got.id).toBe("p1");
    const [url, init] = call(fetchMock);
    expect(url).toBe(`${BASE}/v1/investigations/inv-1/link-types`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(input);
  });

  it("gives the server's own sentence for a refused name", async () => {
    stub(422, { error: "proposal_refused", detail: "ASSOCIATE_OF is already a type in the ontology: use it instead." });
    const error = await proposeLinkType(BASE, "tok", "inv-1", {
      name: "ASSOCIATE_OF", from_types: ["Person"], to_types: ["Person"], directed: false, reason: "r",
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(LinkTypeError);
    expect((error as LinkTypeError).kind).toBe("refused");
    expect((error as LinkTypeError).message).toContain("already a type");
  });

  it("says forbidden for a Viewer and not found for another case's proposal", async () => {
    stub(403, { detail: "too low" });
    await expect(withdrawProposal(BASE, "tok", "inv-1", "p1", "x")).rejects.toMatchObject({ kind: "forbidden" });
    stub(404, { error: "proposal_not_found" });
    await expect(withdrawProposal(BASE, "tok", "inv-1", "p1", "x")).rejects.toMatchObject({ kind: "not_found" });
  });
});

describe("the administrator's decisions", () => {
  it("lists the unit's proposals", async () => {
    const fetchMock = stub(200, { proposals: [{ id: "p1" }] });
    expect((await listProposals(BASE, "tok")).map((p) => p.id)).toEqual(["p1"]);
    expect(call(fetchMock)[0]).toBe(`${BASE}/v1/admin/link-types`);
  });

  it("promotes with the basis, the reason and a new name only when one is given", async () => {
    const fetchMock = stub(200, { id: "p1", status: "promoted" });
    await promoteProposal(BASE, "tok", "p 1", { basis: "direct", reason: "A loader backs it" });
    expect(call(fetchMock)[0]).toBe(`${BASE}/v1/admin/link-types/p%201/promote`);
    expect(JSON.parse(String(call(fetchMock)[1].body))).toEqual({ basis: "direct", reason: "A loader backs it" });
    await promoteProposal(BASE, "tok", "p1", { basis: "probabilistic", reason: "r", rename_to: "KNOWS_STAFF_AT" });
    expect(JSON.parse(String(call(fetchMock, 1)[1].body)).rename_to).toBe("KNOWS_STAFF_AT");
  });

  it("rejects and retires with a reason", async () => {
    const fetchMock = stub(200, { proposals: [] });
    await rejectProposal(BASE, "tok", "p1", "Use ASSOCIATE_OF");
    await retireLinkType(BASE, "tok", "KNOWN_TO", "Superseded");
    expect(call(fetchMock, 0)[0]).toBe(`${BASE}/v1/admin/link-types/p1/reject`);
    expect(call(fetchMock, 1)[0]).toBe(`${BASE}/v1/admin/link-types/retire`);
    expect(JSON.parse(String(call(fetchMock, 1)[1].body))).toEqual({ name: "KNOWN_TO", reason: "Superseded" });
  });
});
