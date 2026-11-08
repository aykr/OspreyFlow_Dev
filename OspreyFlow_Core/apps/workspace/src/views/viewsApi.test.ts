import { afterEach, describe, expect, it, vi } from "vitest";

import { deleteView, listViews, missingNote, openView, saveView, shareView, viewBody } from "./viewsApi";

const API = "http://conduit";

function reply(status: number, body: unknown = {}): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stub(answer: Response) {
  const fetcher = vi.fn(async (..._args: unknown[]) => answer);
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => vi.unstubAllGlobals());

const VIEW = { id: "v1", case_id: "c1", name: "Contacts", created_by: "alice", created_at: "2026-11-08T10:00:00Z", shared: false, chosen: 2 };

describe("viewsApi", () => {
  it("saves a chosen-node view with its layout, window and threshold, as CaseViewInput", async () => {
    const fetcher = stub(reply(201, VIEW));
    const saved = await saveView(API, "t", "c1", {
      name: " Contacts ",
      nodeIds: ["n1", "n2"],
      layout: { n1: { x: 1, y: 2 } },
      window: { validFrom: "2026-01-01T00:00:00Z", validTo: null },
      threshold: 0.7,
    });
    expect(saved).toEqual({ ok: true, view: VIEW });
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/v1/investigations/c1/views`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "Contacts",
      node_ids: ["n1", "n2"],
      layout: { n1: { x: 1, y: 2 } },
      window: { valid_from: "2026-01-01T00:00:00Z", valid_to: null },
      threshold: 0.7,
    });
  });

  it("saves a filtered view with whole days for its dates", () => {
    expect(viewBody({ name: "People", filter: { entityTypes: ["Person"], validFrom: "2026-01-01", validTo: "2026-02-01" } })).toEqual({
      name: "People",
      filter: { entity_types: ["Person"], valid_from: "2026-01-01T00:00:00Z", valid_to: "2026-02-01T23:59:59Z" },
    });
  });

  it("refuses an empty name or an empty selection before asking the server", async () => {
    const fetcher = stub(reply(201, VIEW));
    expect(await saveView(API, "t", "c1", { name: "  ", nodeIds: ["n1"] })).toEqual({ ok: false, message: "Give the view a name." });
    expect((await saveView(API, "t", "c1", { name: "x", nodeIds: [] })).ok).toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("says a refusal to save in words", async () => {
    stub(reply(403, { detail: "forbidden" }));
    expect(await saveView(API, "t", "c1", { name: "x", nodeIds: ["n1"] })).toEqual({
      ok: false,
      message: "Saving a view needs the right to work this case.",
    });
  });

  it("lists the views the server gives, and only those", async () => {
    stub(reply(200, [VIEW]));
    expect(await listViews(API, "t", "c1")).toEqual([VIEW]);
  });

  it("shares and deletes through the view's own routes", async () => {
    const fetcher = stub(reply(200, { ...VIEW, shared: true }));
    expect(await shareView(API, "t", "c1", "v1")).toEqual({ ok: true });
    expect(fetcher.mock.calls[0]?.[0]).toBe(`${API}/v1/investigations/c1/views/v1/share`);
    const deleting = stub(reply(204));
    expect(await deleteView(API, "t", "c1", "v1")).toEqual({ ok: true });
    expect((deleting.mock.calls[0]?.[1] as RequestInit).method).toBe("DELETE");
  });

  it("says only the creator shares or deletes, when a member who can see it tries", async () => {
    stub(reply(403, { error: "not_the_views_creator" }));
    expect(await shareView(API, "t", "c1", "v1")).toEqual({ ok: false, message: "Only the person who saved this view can share it." });
    stub(reply(403, { error: "not_the_views_creator" }));
    expect(await deleteView(API, "t", "c1", "v1")).toEqual({ ok: false, message: "Only the person who saved this view can delete it." });
  });

  it("opens a view, or says it is not found, never why", async () => {
    const opened = { view: VIEW, nodes: [], edges: [], layout: {}, missing: 1 };
    stub(reply(200, opened));
    expect(await openView(API, "t", "c1", "v1")).toEqual({ ok: true, opened });
    stub(reply(404, { error: "view_not_found" }));
    expect(await openView(API, "t", "c1", "v1")).toEqual({ ok: false, kind: "not_found" });
  });

  it("passes a view past the cap on as the typed limit_exceeded, with its own figures", async () => {
    const limit = { error: "limit_exceeded", cap_kind: "nodes", cap: 10, would_be: 12, options: ["save_as_view", "filter", "promote_to_batch"] };
    stub(reply(409, limit));
    expect(await openView(API, "t", "c1", "v1")).toEqual({ ok: false, kind: "limit_exceeded", wouldBe: limit });
  });

  it("counts what it could not show without saying why", () => {
    expect(missingNote(0)).toBeNull();
    expect(missingNote(1)).toBe("1 item in this view could not be shown");
    expect(missingNote(3)).toBe("3 items in this view could not be shown");
  });
});
