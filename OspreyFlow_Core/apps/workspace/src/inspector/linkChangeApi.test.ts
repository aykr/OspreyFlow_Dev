import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkChangeError, changeLink, fetchLinkHistory } from "./linkChangeApi";

afterEach(() => vi.unstubAllGlobals());

const BASE = "http://api.test";

function stub(status: number, json: unknown) {
  const fetchMock = vi.fn(async () => ({ ok: status >= 200 && status < 300, status, json: async () => json }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("changeLink", () => {
  it("posts the change with its reason to the link's own route and returns the result", async () => {
    const result = { edge: { id: "e2" }, delta: { op: "replace_edge", seq: 3 }, change: { id: "c1" } };
    const fetchMock = stub(200, result);
    const got = await changeLink(BASE, "tok", "inv 1", "e/1", {
      reason: "Told so",
      type: "FAMILY_OF",
      properties: { relation: "cousin" },
    });
    expect(got).toEqual(result);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${BASE}/v1/investigations/inv%201/links/e%2F1/change`);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    expect(JSON.parse(String(init.body))).toEqual({
      reason: "Told so",
      type: "FAMILY_OF",
      properties: { relation: "cousin" },
    });
  });

  it("sends a cleared validity period as an explicit null, and leaves a field out when it is left alone", async () => {
    const fetchMock = stub(200, { edge: {}, delta: {}, change: {} });
    await changeLink(BASE, "tok", "inv-1", "e1", { reason: "r", interval: null });
    const sent = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(sent).toEqual({ reason: "r", interval: null });
    expect("type" in sent).toBe(false);
  });

  it.each([
    [404, { error: "link_not_found" }, "link_not_found"],
    [422, { error: "invalid_link_change", detail: "Say why." }, "invalid"],
    [422, { error: "nothing_changed", detail: "Nothing about the link would change." }, "nothing_changed"],
    [422, { error: "resolution_link", detail: "Same-as links are confirmed." }, "resolution_link"],
    [403, { detail: "no" }, "forbidden"],
    [500, {}, "failed"],
  ])("a %i answer is a %s refusal carrying the server's own sentence", async (status, body, kind) => {
    stub(status, body);
    const error = await changeLink(BASE, "tok", "inv-1", "e1", { reason: "r" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(LinkChangeError);
    expect((error as LinkChangeError).kind).toBe(kind);
    if ("detail" in body && status === 422) expect((error as LinkChangeError).message).toBe(body.detail);
  });

  it("treats a network failure as a failure to save, not a silent success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    const error = await changeLink(BASE, "tok", "inv-1", "e1", { reason: "r" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(LinkChangeError);
    expect((error as LinkChangeError).kind).toBe("failed");
  });
});

describe("fetchLinkHistory", () => {
  it("reads the history of the link", async () => {
    const fetchMock = stub(200, { changes: [{ id: "c1", reason: "Told so" }], truncated: false });
    const got = await fetchLinkHistory(BASE, "tok", "inv-1", "e2");
    expect(got.changes).toHaveLength(1);
    expect(got.truncated).toBe(false);
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe(
      `${BASE}/v1/investigations/inv-1/links/e2/history`,
    );
  });

  it("an answer that is not a history is a failure, not an empty history", async () => {
    stub(200, {});
    const error = await fetchLinkHistory(BASE, "tok", "inv-1", "e2").catch((e: unknown) => e);
    expect((error as LinkChangeError).kind).toBe("failed");
  });

  it("a link the person may not see is the same refusal as one that is not there", async () => {
    stub(404, { error: "link_not_found" });
    const error = await fetchLinkHistory(BASE, "tok", "inv-1", "e2").catch((e: unknown) => e);
    expect((error as LinkChangeError).kind).toBe("link_not_found");
  });
});
