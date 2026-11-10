// @vitest-environment jsdom
// L3.6 (ADR-143 Amendment 2 decision 8) in the Glass: a drawn watch's alert in the one queue, named
// for what it is, filtered by its kind, and *Open the board* opening the board its drawn item names
// — offered only for that kind, and only when the explanation the reader was given holds the drawn
// item (an alert over a drawn item the reader may not see is never listed nor explained: the
// Conduit's, `test_drawn_watch_queue.py`).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertQueue, alertTitle, drawnBoard } from "./AlertQueue";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const API = { apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" };
const handling = { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" };
const audit = { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 };
const drawnItem = {
  id: "d1", type: "Person", properties: { family_name: "Tall" }, handling, audit, datasets: ["layer"],
  provenance: { state: "asserted", sources: [], first_seen: "2026-11-01T00:00:00Z",
    drawn: { item_id: "i1", asserted_by: "me", board_id: "board-7", case_id: "c1", label: "Tall",
             grading: { scheme: "3x5x2", source: "B", intelligence: "2", handling: "P" } } },
}; // prettier-ignore
const loaded = {
  id: "p1", type: "Person", properties: { family_name: "TALL", given_names: "Jordan" }, handling, audit, datasets: ["src"],
  provenance: { state: "asserted", sources: [{ document_id: "in/nominals.csv", locator: "row 3", excerpt_hash: "a" }], first_seen: "2026-11-01T00:00:00Z" },
}; // prettier-ignore
const row = {
  alert: { id: "w1", rule_id: "drawn_watch:watch-1", owner_id: "me", mode: "full", investigation_id: "c1", assignee: null,
           created_at: "2026-11-10T07:00:00Z", referent_node_ids: ["d1", "p1"], status: "open", dataset_id: "src",
           words: "A load met a drawn item: p1 looks like d1 (the same pnc_id)." },
  summary: "A load met a drawn item: Jordan TALL looks like Tall (the same pnc_id).",
  kind: "drawn_watch", severity: "medium", audience: "owner", team: null,
}; // prettier-ignore

function serve(routes: Record<string, unknown>, calls: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = new URL(url);
      const path = u.pathname.replace("/v1/investigations/c1/", "");
      calls.push(`${init?.method ?? "GET"} ${path}${u.search}`);
      const found = routes[`${init?.method ?? "GET"} ${path}`];
      return found === undefined ? json(404, {}) : json(200, found);
    }),
  );
  return calls;
}

describe("a drawn watch's alert", () => {
  it("is named for what it is, and its board is the one its drawn item names", () => {
    expect(alertTitle(row.alert as never, "drawn_watch")).toBe("A load met a drawn item");
    expect(drawnBoard([loaded, drawnItem] as never)).toBe("board-7");
    expect(drawnBoard([loaded] as never)).toBeNull();
  });

  it("opens the board its drawn item names, from the alert's detail", async () => {
    serve({ "GET alert-queue": [row], "GET alert-queue/w1": { ...row, nodes: [drawnItem, loaded], edges: [], transactions: [] } });
    const onOpenBoard = vi.fn();
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="w1" onOpenBoard={onOpenBoard} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open the board" }));
    expect(onOpenBoard).toHaveBeenCalledWith("board-7");
    expect(screen.getByText("A load met a drawn item · Medium severity · Only its owner")).toBeTruthy();
  });

  it("offers no board when the explanation holds no drawn item, nor for another kind", async () => {
    serve({ "GET alert-queue": [row], "GET alert-queue/w1": { ...row, nodes: [loaded], edges: [], transactions: [] } });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="w1" onOpenBoard={vi.fn()} />);
    await screen.findByRole("region", { name: "What fired this alert" });
    expect(screen.queryByRole("button", { name: "Open the board" })).toBeNull();
    cleanup();
    const monitor = { ...row, alert: { ...row.alert, id: "m1", rule_id: "monitor:x" }, kind: "monitor" };
    serve({ "GET alert-queue": [monitor], "GET alert-queue/m1": { ...monitor, nodes: [drawnItem, loaded], edges: [], transactions: [] } });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="m1" onOpenBoard={vi.fn()} />);
    await screen.findByRole("region", { name: "What fired this alert" });
    expect(screen.queryByRole("button", { name: "Open the board" })).toBeNull();
  });

  it("is filtered by its kind in the query", async () => {
    const calls = serve({ "GET alert-queue": [row] });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "Kind of alert" }), { target: { value: "drawn_watch" } });
    await waitFor(() => expect(calls.some((c) => c.startsWith("GET alert-queue?") && c.includes("kind=drawn_watch"))).toBe(true));
  });
});
