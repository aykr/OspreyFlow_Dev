// @vitest-environment jsdom
//
// The Glass's own side of ADR-052: it lists the cases the account holds a level on and creates a
// named one. It enforces nothing (ADR-050: the Conduit does); these prove it asks the right routes
// and turns their refusals into readable messages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";
import { caseUrl, createCase, listCases, openCase } from "./cases";

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

  it("remembers it for the sign-in round trip before navigating", () => {
    const navigate = vi.fn();

    openCase("case-9", undefined, navigate);

    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("case-9");
    expect(navigate).toHaveBeenCalledWith("/?investigation=case-9&from=case");
  });
});
