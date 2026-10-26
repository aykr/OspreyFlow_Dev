// Add many from a list (ADR-128 decision 1, B2): what the Glass sends and says. It sends the typed
// strings and receives four counts and, once confirmed, the delta to draw; it is never given an
// identifier back, and a refusal is said in words with the figure (rule 2).
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AddFromListError,
  addIdentifiers,
  countIdentifiers,
  countSentence,
  listFromFile,
  MAX_IDENTIFIERS,
} from "./addFromListApi";

afterEach(() => vi.unstubAllGlobals());

const COUNTS = { read: 40, found: 38, matched_nothing: 2, repeated: 1 };

function stub(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async () => ({ ok: status < 300, status, json: async () => body }));
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("the count, in words", () => {
  it("says the four figures in the order the analyst reads them", () => {
    expect(countSentence(COUNTS)).toBe("40 identifiers read. 38 found. 2 matched nothing you can see. 1 repeated.");
  });

  it("says one identifier in the singular and groups thousands", () => {
    expect(countSentence({ read: 1, found: 1, matched_nothing: 0, repeated: 0 })).toBe(
      "1 identifier read. 1 found. 0 matched nothing you can see. 0 repeated.",
    );
    expect(countSentence({ read: 5000, found: 4999, matched_nothing: 1, repeated: 0 })).toContain("5,000 identifiers read.");
  });
});

describe("what a file gives", () => {
  it("takes a .csv's first column, a quoted cell unquoted and kept whole", () => {
    const csv = 'identifier,name\nZ1234ZZ,Smith\n"07700 900123",x\r\nQQ123456A\n';
    expect(listFromFile("cohort.csv", csv)).toBe("identifier\nZ1234ZZ\n07700 900123\nQQ123456A");
  });

  it("takes a .txt whole, since its lines are the list", () => {
    expect(listFromFile("cohort.txt", "Z1234ZZ\nZ2345ZZ, Z3456ZZ\n")).toBe("Z1234ZZ\nZ2345ZZ, Z3456ZZ");
  });

  it("drops a leading byte-order mark", () => {
    expect(listFromFile("a.txt", "\uFEFFZ1234ZZ")).toBe("Z1234ZZ");
  });
});

describe("the count request", () => {
  it("asks for the count alone, with the typed text as it is", async () => {
    const mock = stub(200, { counts: COUNTS, added: null });
    const counts = await countIdentifiers("http://api", "tok", "case 1", "Z1234ZZ\n07700 900123");
    expect(counts).toEqual(COUNTS);
    const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations/case%201/working-set/add-by-identifiers");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      identifiers: ["Z1234ZZ\n07700 900123"],
      confirm: false,
      with_links: false,
    });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
});

describe("the add request", () => {
  const DELTA = { seq: 4, op: "add", nodes: [{ id: "n1" }, { id: "n2" }], edges: [] };

  it("confirms, by default without links, and hands back the delta", async () => {
    const mock = stub(200, { counts: COUNTS, added: { delta: DELTA, links_among: "not_asked" } });
    const result = await addIdentifiers("http://api", "tok", "c", "Z1234ZZ", false);
    expect(result.delta).toEqual(DELTA);
    expect(result.counts).toEqual(COUNTS);
    const init = mock.mock.calls[0]![1] as unknown as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({ confirm: true, with_links: false });
  });

  it("asks for the links when the analyst chose them", async () => {
    const mock = stub(200, { counts: COUNTS, added: { delta: DELTA, links_among: "added" } });
    await addIdentifiers("http://api", "tok", "c", "Z1234ZZ", true);
    expect(JSON.parse(String((mock.mock.calls[0]![1] as unknown as RequestInit).body))).toMatchObject({
      confirm: true,
      with_links: true,
    });
  });
});

describe("a refusal is said in words, with the figure", () => {
  it("names the limit of 5,000 and says nothing was added", async () => {
    stub(413, { error: "too_many_identifiers", cap: 5000, received: 5001, message: "ignored" });
    await expect(countIdentifiers("http://api", "t", "c", "x")).rejects.toThrow(
      new AddFromListError("5,001 identifiers is more than one request reads, which is 5,000. Nothing was added. Split the list and add it in parts."),
    );
    expect(MAX_IDENTIFIERS).toBe(5000);
  });

  it("says the canvas would be past its limit, with the three options, and that nothing was added", async () => {
    stub(409, {
      error: "limit_exceeded",
      cap_kind: "nodes",
      cap: 50000,
      would_be: 50002,
      options: ["branch", "filter", "promote_to_batch"],
    });
    const failure = await addIdentifiers("http://api", "t", "c", "x", false).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(AddFromListError);
    expect((failure as Error).message).toBe(
      "Too many for the canvas: 50,002 nodes against a limit of 50,000. Nothing was added. You can branch the case, filter it to part, or promote the list to a batch.",
    );
  });

  it("says Editor access is needed", async () => {
    stub(403, {});
    await expect(addIdentifiers("http://api", "t", "c", "x", false)).rejects.toThrow("Adding to this case needs Editor access.");
  });

  it("says the server could not be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("down"))));
    await expect(countIdentifiers("http://api", "t", "c", "x")).rejects.toThrow("The server could not be reached.");
  });

  it("says any other failure with its status", async () => {
    stub(500, {});
    await expect(countIdentifiers("http://api", "t", "c", "x")).rejects.toThrow("The list could not be read (500).");
  });
});
