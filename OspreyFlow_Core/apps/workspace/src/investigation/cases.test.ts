// @vitest-environment jsdom
//
// The Glass's own side of ADR-052: it lists the cases the account holds a level on and creates a
// named one. It enforces nothing (ADR-050: the Conduit does); these prove it asks the right routes
// and turns their refusals into readable messages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";
import { type CaseListing, caseUrl, createCase, listCases, nestCases, openCase, removeCase } from "./cases";

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
    expect(JSON.parse(init.body as string)).toEqual({ name: "Enron" });
    expect(created.id).toBe("new-1");
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

describe("branch tabs (ADR-084)", () => {
  const made = (id: string, branchedFrom: string | null, at: string, extra = {}) => ({
    id,
    name: id,
    level: "author" as const,
    created_at: at,
    created_by: "a",
    branched_from: branchedFrom,
    ...extra,
  });

  it("puts a case's own branches in one family, root first, oldest branch first", async () => {
    const { branchFamily } = await import("./cases");
    const cases = [
      made("b2", "root", "2026-10-03T00:00:00Z"),
      made("other", null, "2026-10-01T00:00:00Z"),
      made("root", null, "2026-10-01T00:00:00Z"),
      made("b1", "root", "2026-10-02T00:00:00Z"),
    ];
    const family = branchFamily(cases, "b2");
    expect(family?.root.id).toBe("root");
    expect(family?.branches.map((c) => c.id)).toEqual(["b1", "b2"]);
  });

  it("follows a branch of a branch up to the original case", async () => {
    const { branchFamily } = await import("./cases");
    const cases = [
      made("root", null, "2026-10-01T00:00:00Z"),
      made("b1", "root", "2026-10-02T00:00:00Z"),
      made("b1a", "b1", "2026-10-03T00:00:00Z"),
    ];
    const family = branchFamily(cases, "b1a");
    expect(family?.root.id).toBe("root");
    expect(family?.branches.map((c) => c.id)).toEqual(["b1", "b1a"]);
  });

  it("treats the topmost case this account can see as the root when the original is not listed", async () => {
    const { branchFamily } = await import("./cases");
    const cases = [made("b1", "gone", "2026-10-02T00:00:00Z")];
    const family = branchFamily(cases, "b1");
    expect(family?.root.id).toBe("b1");
    expect(family?.branches).toEqual([]);
  });

  it("has no family for a case that is not in the list", async () => {
    const { branchFamily } = await import("./cases");
    expect(branchFamily([], "nope")).toBeNull();
  });

  it("shows the open branches and the current one, and holds the closed ones back", async () => {
    const { branchFamily, openTabs } = await import("./cases");
    const cases = [
      made("root", null, "2026-10-01T00:00:00Z"),
      made("b1", "root", "2026-10-02T00:00:00Z", { tab_hidden: true }),
      made("b2", "root", "2026-10-03T00:00:00Z"),
      made("b3", "root", "2026-10-04T00:00:00Z", { tab_hidden: true }),
    ];
    const family = branchFamily(cases, "b3")!;
    // b3 is hidden but it is the one on screen, so it stays in the strip.
    expect(openTabs(family, "b3").map((c) => c.id)).toEqual(["b2", "b3"]);
    expect(openTabs(family, "root").map((c) => c.id)).toEqual(["b2"]);
  });

  it("asks the tab route for exactly the case and the yes or no", async () => {
    const { setTabHidden } = await import("./cases");
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) });
    await setTabHidden("http://api", "tok", "b1", true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations/b1/tab");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ hidden: true });
  });

  it("says so when the tab could not be closed, and does not pretend", async () => {
    const { setTabHidden } = await import("./cases");
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) });
    await expect(setTabHidden("http://api", "tok", "b1", true)).rejects.toThrow(/not found/i);
  });
});

// The case picker lists each original case once with its branches indented beneath it (ADR-084
// Amendment 3). The owner, 4 October 2026: three "Enron corpus · n selected" rows sat in the main
// list beside the cases they came from, with nothing saying they were branches.
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
