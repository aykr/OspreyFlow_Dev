// @vitest-environment jsdom
//
// The Glass's own side of ADR-052: it lists the cases the account holds a level on and creates a
// named one. It enforces nothing (ADR-050: the Conduit does); these prove it asks the right routes
// and turns their refusals into readable messages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";
import { type CaseListing, caseIsOpenable, caseUrl, createCase, listCases, nestCases, openCase, removeCase } from "./cases";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
});
afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function respond(status: number, body: unknown): void {
  fetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("listCases", () => {
  it("asks for the caller's cases with the bearer token", async () => {
    respond(200, [
      { id: "c1", name: "Fixture", level: "author", created_at: "2026-09-29T00:00:00Z", created_by: "a" },
    ]);

    const cases = await listCases("http://api", "tok");

    expect(fetchMock).toHaveBeenCalledWith("http://api/v1/investigations", {
      headers: { Authorization: "Bearer tok" },
    });
    expect(cases.map((c) => [c.id, c.name, c.level])).toEqual([["c1", "Fixture", "author"]]);
  });

  it("says so when the request fails, not an empty list", async () => {
    respond(500, {});

    await expect(listCases("http://api", "tok")).rejects.toThrow(/could not load your cases/i);
  });
});

describe("createCase", () => {
  it("posts the trimmed name and returns the new case", async () => {
    respond(201, { id: "new-1", name: "Enron" });

    const created = await createCase("http://api", "tok", "  Enron  ");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "Enron", domains: [] });
    expect(created.id).toBe("new-1");
  });

  it("sends the domain models chosen, sorted as the catalogue lists them", async () => {
    respond(201, { id: "new-1", name: "Enron", domains: ["fibo", "niem"] });

    await createCase("http://api", "tok", "Enron", [], ["niem", "fibo"]);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ name: "Enron", domains: ["fibo", "niem"] });
  });

  it("refuses a blank name without calling the server", async () => {
    await expect(createCase("http://api", "tok", "   ")).rejects.toThrow(/name/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("opening a case", () => {
  it("names the case in the URL the Glass already reads", () => {
    expect(caseUrl("abc 1")).toBe("/?investigation=abc%201&from=case");
  });

  it("asks the Glass to sign back in on arrival, and to reopen the Ingest tab when it was there", () => {
    expect(caseUrl("c1", "ingest")).toBe("/?investigation=c1&from=case&view=ingest");
  });

  it("opens a case branched for questions on its Questions panel (ADR-098 decision 4)", () => {
    expect(caseUrl("b1", "questions")).toBe("/?investigation=b1&from=case&view=questions");
  });

  it("remembers it for the sign-in round trip before navigating", () => {
    const navigate = vi.fn();

    openCase("case-9", undefined, navigate);

    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("case-9");
    expect(navigate).toHaveBeenCalledWith("/?investigation=case-9&from=case");
  });
});


describe("removing a case", () => {
  it("sends a DELETE for that case with the bearer token", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await removeCase("http://api", "tok", "c 1");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations/c%201");
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("says plainly when the server refuses, and does not pretend it worked", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 403 })));
    await expect(removeCase("http://api", "tok", "c1")).rejects.toThrow(/permission/i);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404 })));
    await expect(removeCase("http://api", "tok", "c1")).rejects.toThrow(/not found|already/i);
  });

  it("forgets the case if it was the one remembered for this tab", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204 })));
    sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, "c1");
    await removeCase("http://api", "tok", "c1");
    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBeNull();
    sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, "other");
    await removeCase("http://api", "tok", "c1");
    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("other");
  });
});

describe("nestCases", () => {
  function listing(id: string, created: string, branchedFrom: string | null = null, name = id): CaseListing {
    return { id, name, level: "author", created_at: created, created_by: "a", branched_from: branchedFrom };
  }

  it("puts each case's branches beneath it, oldest branch first, roots in the usual order", () => {
    const cases = [
      listing("enron", "2026-10-01T00:00:00Z"),
      listing("b4", "2026-10-04T12:00:00Z", "enron"),
      listing("b2", "2026-10-04T10:00:00Z", "enron"),
      listing("fixture", "2026-10-02T00:00:00Z"),
      listing("b2-of-b2", "2026-10-04T11:00:00Z", "b2"),
    ];
    expect(nestCases(cases).map(({ entry, branch }) => [entry.id, branch])).toEqual([
      ["fixture", false],
      ["enron", false],
      ["b2", true],
      ["b2-of-b2", true],
      ["b4", true],
    ]);
  });

  it("lists a branch whose original the account cannot see under its oldest visible ancestor", () => {
    const cases = [listing("b2", "2026-10-04T10:00:00Z", "not-visible"), listing("b3", "2026-10-04T11:00:00Z", "b2")];
    expect(nestCases(cases).map(({ entry, branch }) => [entry.id, branch])).toEqual([
      ["b2", false],
      ["b3", true],
    ]);
  });

  it("drops no case", () => {
    const cases = [listing("a", "2026-01-01T00:00:00Z"), listing("b", "2026-01-02T00:00:00Z", "a")];
    expect(nestCases(cases)).toHaveLength(2);
  });
});

describe("datasetLabel (ADR-099 Amendment 6)", () => {
  it("is the name and the id, the id shortened to its last five characters past twelve", async () => {
    const { datasetLabel } = await import("./cases");
    expect(datasetLabel("enron", "Enron corpus")).toBe("Enron corpus · enron");
    expect(datasetLabel("01K9XQ0000000000000000ABCD", "Enron corpus")).toBe("Enron corpus · …0ABCD");
  });
});

// 9 October 2026: after signing in as a second account, the Glass reopened the first account's case
// from the tab's session and every panel was refused (404). A case the account cannot open is
// dropped, so the picker shows; a server that is merely failing does not drop it.
describe("caseIsOpenable", () => {
  const answer = (status: number) => vi.fn(async () => new Response("{}", { status }));
  it.each([[404], [403]])("is false when the case is refused (%i)", async (status) => {
    vi.stubGlobal("fetch", answer(status));
    expect(await caseIsOpenable("http://test.invalid", "tok", "inv-1")).toBe(false);
  });
  it.each([[200], [500], [503]])("is true otherwise (%i)", async (status) => {
    vi.stubGlobal("fetch", answer(status));
    expect(await caseIsOpenable("http://test.invalid", "tok", "inv-1")).toBe(true);
  });
  it("is true when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    expect(await caseIsOpenable("http://test.invalid", "tok", "inv-1")).toBe(true);
  });
});

// ADR-084 Amendment 4 (the owner, 14 October 2026: "the current display method for the Branch and main
// case is very confusing, i need a method to delete a branch as through the Glass view").
describe("a branch, named and placed in its case's tree", () => {
  const listing = (over: Partial<CaseListing>): CaseListing => ({
    id: "x", name: "", level: "author", created_at: "2026-10-14T16:40:00Z", created_by: "a", ...over,
  });

  it("is called by its size and when it was made, unless someone renamed it", async () => {
    const { branchLabel } = await import("./cases");
    expect(branchLabel(listing({ name: "Branch of Operation Ledger (synthetic demo) (2 nodes)" }))).toBe("2 nodes · 14 Oct 16:40");
    expect(branchLabel(listing({ name: "Branch of Operation Ledger (1 node)" }))).toBe("1 node · 14 Oct 16:40");
    expect(branchLabel(listing({ name: "Branch of Enron (2)" }))).toBe("Branch · 14 Oct 16:40");
    expect(branchLabel(listing({ name: "Midland Pallets route" }))).toBe("Midland Pallets route");
  });

  it("goes back to the case it came from, or the oldest one this account can see", async () => {
    const { returnFor } = await import("./cases");
    const root = listing({ id: "r" });
    const b1 = listing({ id: "b1", branched_from: "r" });
    const b2 = listing({ id: "b2", branched_from: "b1" });
    const orphan = listing({ id: "o", branched_from: "gone" });
    expect(returnFor([root, b1, b2], "b2")?.id).toBe("b1");
    expect(returnFor([root, b1, b2], "b1")?.id).toBe("r");
    expect(returnFor([root, b1, b2], "r")).toBeNull();
    expect(returnFor([orphan], "o")).toBeNull();
  });

  it("is renamed through the case's own route, refused in words", async () => {
    const { renameCase } = await import("./cases");
    const calls: [string, RequestInit][] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return new Response("{}", { status: calls.length === 1 ? 200 : 403 });
    }));
    await renameCase("http://test.invalid", "tok", "b1", "  Midland Pallets route ");
    expect(calls[0]?.[0]).toBe("http://test.invalid/v1/investigations/b1");
    expect(calls[0]?.[1].method).toBe("PATCH");
    expect(JSON.parse(String(calls[0]?.[1].body))).toEqual({ name: "Midland Pallets route" });
    await expect(renameCase("http://test.invalid", "tok", "b1", "x")).rejects.toThrow(
      "Only the case's Author can rename it.",
    );
  });
});
