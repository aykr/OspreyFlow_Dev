// @vitest-environment jsdom
//
// The Glass's own side of ADR-052: it lists the cases the account holds a level on and creates a
// named one. It enforces nothing (ADR-050: the Conduit does); these prove it asks the right routes
// and turns their refusals into readable messages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";
import { caseIsOpenable, caseUrl, createCase, listCases, openCase, openCaseView, removeCase, setCaseDatasets } from "./cases";

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

    const created = await createCase("http://api", "tok", "  Enron  ", { datasetId: "enron" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "Enron", dataset_ids: ["enron"], domains: [] });
    expect(created.id).toBe("new-1");
  });

  it("sends the domain models chosen, sorted as the catalogue lists them", async () => {
    respond(201, { id: "new-1", name: "Enron", domains: ["fibo", "niem"] });

    await createCase("http://api", "tok", "Enron", { newDatasetName: "Enron data" }, ["niem", "fibo"]);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      name: "Enron",
      new_dataset_name: "Enron data",
      domains: ["fibo", "niem"],
    });
  });

  it("refuses a blank name without calling the server", async () => {
    await expect(createCase("http://api", "tok", "   ", { newDatasetName: "" })).rejects.toThrow(/name/i);
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

  it("opens a case on its Questions panel (ADR-098 decision 4)", () => {
    expect(caseUrl("c1", "questions")).toBe("/?investigation=c1&from=case&view=questions");
  });

  it("opens a case on one of its views, as a lens (ADR-144)", () => {
    const navigate = vi.fn();
    openCaseView("case-9", "view 1", navigate);
    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("case-9");
    expect(navigate).toHaveBeenCalledWith("/?investigation=case-9&from=case&case_view=view%201");
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
    // L3.H1: a dataset's home case is refused in the Conduit's own words, never a bare 409.
    const kept = { detail: { error: "home_case_kept", message: "this is its dataset's home case, which holds the dataset's reports, alerts and promotion reviews, so it is kept while the dataset exists" } };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409, json: async () => kept })));
    await expect(removeCase("http://api", "tok", "c1")).rejects.toThrow(
      "This case cannot be removed: this is its dataset's home case, which holds the dataset's reports, alerts and promotion reviews, so it is kept while the dataset exists.",
    );
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

describe("changing what a case reads (L3.H1)", () => {
  it("refuses a dataset's home case in the Conduit's own words", async () => {
    const kept = { detail: { error: "home_case_kept", message: "this is its dataset's home case, which holds the dataset's reports, alerts and promotion reviews, so it keeps reading its dataset while the dataset exists" } };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409, json: async () => kept })));
    await expect(setCaseDatasets("http://api", "tok", "home-1", ["ds-b"])).rejects.toThrow(
      "This case's dataset cannot be changed: this is its dataset's home case, which holds the dataset's reports, alerts and promotion reviews, so it keeps reading its dataset while the dataset exists.",
    );
  });
});
