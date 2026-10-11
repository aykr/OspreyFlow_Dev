// @vitest-environment jsdom
// ADR-113 stage 5: the Packs tab — what is withheld is said by number and never shown, order changes
// send exactly the items that were shown, only a trend can be refreshed, a note is never marked for
// the analyst, a publication refused for withheld items says so, and a withdrawal sends its reason.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PacksTab } from "./PacksTab";
import { ASSESSMENT_ITEM, NOTE_ITEM, PACK, PUBLISHED_PACK, TREND_ITEM, draft, json, serve, type Call } from "./reportsTestKit";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const STATEMENT = "The two firms share a director";

function routes(extra: (call: Call) => Response | null = () => null, pack = PACK, over = {}) {
  return (call: Call) =>
    extra(call) ??
    (call.method === "GET" && call.path === "packs" ? json(200, [pack])
      : call.method === "GET" && call.path === "packs/p1" ? json(200, draft({ pack, ...over }))
      : call.method === "GET" && call.path === "trends" ? json(200, [{ id: "t1", title: "Payments by channel" }])
      : call.method === "GET" && call.path === "judgements" ? json(200, { judgements: [{ id: "j1", statement: STATEMENT }] })
      : call.path === "/v1/handling-scheme" ? json(200, { classification: ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"] })
      : null);  // prettier-ignore
}

function place(canExport = false) {
  render(<PacksTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canExport={canExport} />);
}

async function openPack(title = /Quarter pack/) {
  fireEvent.click(await screen.findByRole("button", { name: title }));
  await screen.findByRole("heading", { name: "Quarter pack" });
}

describe("the pack list", () => {
  it("says which packs are drafts and which are published", async () => {
    serve(routes(() => null, PUBLISHED_PACK));
    place();
    expect(await screen.findByRole("button", { name: "Quarter pack · Published v1" })).toBeTruthy();
  });

  it("creates a pack from its title", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs" ? json(201, PACK) : null)));
    place();
    await screen.findByText("No packs have been made in this case yet.");
    fireEvent.change(screen.getByLabelText("New pack title"), { target: { value: "Quarter pack" } });
    fireEvent.click(screen.getByRole("button", { name: "Create pack" }));
    await screen.findByRole("heading", { name: "Quarter pack" });
    expect(calls.find((c) => c.method === "POST" && c.path === "packs")?.body).toEqual({ title: "Quarter pack" });
  });
});

describe("a pack's items", () => {
  it("says how many are withheld, and shows nothing for them", async () => {
    serve(routes(() => null, PACK, { withheld: 2 }));
    place();
    await openPack();
    expect(screen.getByText("2 items in this pack are withheld from you.")).toBeTruthy();
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByRole("article", { name: `Assessment: ${STATEMENT}` }).textContent).toContain("Marked OFFICIAL-SENSITIVE");
  });

  it("says nothing of withholding when nothing is withheld", async () => {
    serve(routes());
    place();
    await openPack();
    expect(screen.queryByText(/withheld from you/)).toBeNull();
  });

  it("moves an item down by sending exactly the shown ids, swapped", async () => {
    const calls = serve(routes((c) => (c.method === "PUT" && c.path === "packs/p1/order" ? json(200, draft({ items: [ASSESSMENT_ITEM, TREND_ITEM, NOTE_ITEM] })) : null)));
    place();
    await openPack();
    const first = screen.getAllByRole("article")[0] as HTMLElement;
    expect((within(first).getByRole("button", { name: "Move up" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(first).getByRole("button", { name: "Move down" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ item_ids: ["i2", "i1", "i3"] }));
    await waitFor(() => expect(screen.getAllByRole("article")[0]?.getAttribute("aria-label")).toContain("Assessment"));
    const last = screen.getAllByRole("article")[2] as HTMLElement;
    expect((within(last).getByRole("button", { name: "Move down" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("offers Refresh on a trend item only", async () => {
    const calls = serve(routes((c) => (c.path === "packs/p1/items/i1/refresh" ? json(201, { ...TREND_ITEM, id: "i1b" }) : null)));
    place();
    await openPack();
    const [trend, assessment, note] = screen.getAllByRole("article") as HTMLElement[];
    expect(within(trend!).getByRole("button", { name: "Refresh" })).toBeTruthy();
    expect(within(assessment!).queryByRole("button", { name: "Refresh" })).toBeNull();
    expect(within(note!).queryByRole("button", { name: "Refresh" })).toBeNull();
    fireEvent.click(within(trend!).getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "packs/p1/items/i1/refresh")).toBe(true));
  });

  it("removes an item", async () => {
    const calls = serve(routes((c) => (c.method === "DELETE" ? json(204, null) : null)));
    place();
    await openPack();
    fireEvent.click(within(screen.getAllByRole("article")[2] as HTMLElement).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "packs/p1/items/i3")).toBe(true));
  });
});

describe("adding an item", () => {
  it("will not add a note without a marking, and does not mark it for the analyst", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/items" ? json(201, NOTE_ITEM) : null)));
    place();
    await openPack();
    fireEvent.change(screen.getByLabelText("Item kind"), { target: { value: "note" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Handle with care" } });
    const marking = screen.getByLabelText("Note marking") as HTMLSelectElement;
    await waitFor(() => expect(marking.options.length).toBe(4));
    expect(marking.value).toBe("");
    const add = screen.getByRole("button", { name: "Add item" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    expect(screen.getByText("Choose a marking for the note: it is never marked for you.")).toBeTruthy();
    fireEvent.click(add);
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    fireEvent.change(marking, { target: { value: "SECRET" } });
    expect(add.disabled).toBe(false);
    fireEvent.click(add);
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "note", text: "Handle with care", classification: "SECRET" }));
  });

  it("adds a saved trend and an assessment by id", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/items" ? json(201, TREND_ITEM) : null)));
    place();
    await openPack();
    await waitFor(() => expect((screen.getByLabelText("Saved trend") as HTMLSelectElement).options.length).toBe(2));
    fireEvent.change(screen.getByLabelText("Saved trend"), { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Item kind"), { target: { value: "assessment" } });
    await waitFor(() => expect((screen.getByLabelText("Assessment") as HTMLSelectElement).options.length).toBe(2));
    fireEvent.change(screen.getByLabelText("Assessment"), { target: { value: "j1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toEqual([
      { kind: "trend", trend_id: "t1" },
      { kind: "assessment", judgement_id: "j1" },
    ]);
  });
});

describe("publishing and withdrawing", () => {
  it("says a publication refused for withheld items in words", async () => {
    serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/publish" ? json(409, { error: "pack_has_withheld_items", withheld: 2 }) : null)));
    place();
    await openPack();
    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect((await screen.findByRole("alert")).textContent).toBe("2 items in this pack are withheld from you, so you cannot publish it.");
  });

  it("publishes a pack with nothing withheld and says which version", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/publish" ? json(201, { version: 1 }) : null)));
    place();
    await openPack();
    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Published version 1.")).toBeTruthy();
    expect(calls.some((c) => c.method === "POST" && c.path === "packs/p1/publish")).toBe(true);
  });

  it("says each version in words and sends the reason when one is withdrawn", async () => {
    const withdrawn = { ...PUBLISHED_PACK, versions: [
      { version: 1, published_at: "2026-10-03T09:00:00Z", published_by: "ana", withdrawn_at: "2026-10-05T09:00:00Z", withdrawn_by: "ben", withdrawal_reason: "wrong quarter" },
      { version: 2, published_at: "2026-10-11T09:00:00Z", published_by: "ana", withdrawn_at: null, withdrawn_by: null, withdrawal_reason: null },
    ] };  // prettier-ignore
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/versions/2/withdraw" ? json(200, withdrawn) : null), withdrawn));
    place();
    await openPack();
    expect(screen.getByText("Version 1, published 3 October 2026 by ana, withdrawn by ben: wrong quarter")).toBeTruthy();
    expect(screen.getByText("Version 2, published 11 October 2026 by ana")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Withdraw version 1" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Withdraw version 2" }));
    expect((screen.getByRole("button", { name: "Withdraw" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Reason for withdrawing"), { target: { value: "figures were restated" } });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw" }));
    await waitFor(() => expect(calls.find((c) => c.path === "packs/p1/versions/2/withdraw")?.body).toEqual({ reason: "figures were restated" }));
  });

  it("shows earlier snapshots with the date each was replaced", async () => {
    serve(routes((c) => (c.path === "packs/p1/history" ? json(200, { earlier_snapshots: [{ ...TREND_ITEM, id: "old", replaced_at: "2026-10-09T09:00:00Z" }], withheld: 0, versions: [] }) : null)));
    place();
    await openPack();
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Replaced 9 October 2026")).toBeTruthy();
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("offers Export PDF only with the right and a live version", async () => {
    serve(routes(() => null, PUBLISHED_PACK));
    place(true);
    await openPack(/Published v1/);
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeTruthy();
    cleanup();
    serve(routes(() => null, PUBLISHED_PACK));
    place(false);
    await openPack(/Published v1/);
    expect(screen.queryByRole("button", { name: "Export PDF" })).toBeNull();
    cleanup();
    serve(routes());
    place(true);
    await openPack();
    expect(screen.queryByRole("button", { name: "Export PDF" })).toBeNull();
  });
});
