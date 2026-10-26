// @vitest-environment jsdom
//
// 9 October 2026: a refused history route (404 for a case this account cannot open) would have set
// the error body as the list of steps, and rendering it would have thrown. A refusal is an empty
// history, not a crash.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { HistoryPanel } from "./HistoryPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows an empty history when the route refuses", async () => {
  vi.stubGlobal(
    "fetch",
    async () => new Response(JSON.stringify({ error: "investigation_not_found" }), { status: 404 }),
  );
  render(
    <HistoryPanel
      open
      onClose={() => undefined}
      investigationId="inv-1"
      apiBaseUrl="http://test.invalid"
      bearerToken="unused"
      onRestored={() => undefined}
    />,
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("lists each step by its label and Restore, with no size column (ADR-124 decision 8)", async () => {
  // A server that still sent sizes would not have them shown: the column is gone, not hidden.
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(
        JSON.stringify([
          { id: "s1", label: "Seeded", created_at: "2026-10-12T16:42:00Z", node_count: 25, edge_count: 30 },
          { id: "s2", label: "Expanded", created_at: "2026-10-12T16:50:00Z", node_count: 41, edge_count: 52 },
        ]),
      ),
  );
  render(
    <HistoryPanel
      open
      onClose={() => undefined}
      investigationId="inv-1"
      apiBaseUrl="http://test.invalid"
      bearerToken="unused"
      onRestored={() => undefined}
    />,
  );
  const dialog = within(await screen.findByRole("dialog"));
  expect(await dialog.findByText("Seeded")).toBeTruthy();
  expect(dialog.getByText("Expanded")).toBeTruthy();
  expect(dialog.queryByText("Nodes / edges")).toBeNull();
  expect(dialog.queryByText("25 / 30")).toBeNull();
  expect(dialog.queryByText("41 / 52")).toBeNull();
  expect(dialog.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Step", ""]);
});

it("lists a step that holds no canvas snapshot with no Restore (ADR-128: an edit to the case brief)", async () => {
  // Restoring a brief edit would replace the canvas with nothing, so the server marks it not
  // restorable and the panel offers it no button; it is still listed, by its label.
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(
        JSON.stringify([
          { id: "s1", label: "Seeded", created_at: "2026-10-12T16:42:00Z", restorable: true },
          { id: "s2", label: "Edited the brief", created_at: "2026-10-12T16:50:00Z", restorable: false },
          { id: "s3", label: "Expanded", created_at: "2026-10-12T16:55:00Z" },
        ]),
      ),
  );
  render(
    <HistoryPanel
      open
      onClose={() => undefined}
      investigationId="inv-1"
      apiBaseUrl="http://test.invalid"
      bearerToken="unused"
      onRestored={() => undefined}
    />,
  );
  const dialog = within(await screen.findByRole("dialog"));
  expect(await dialog.findByText("Edited the brief")).toBeTruthy();
  const rows = dialog.getAllByRole("row").slice(1);
  expect(rows.map((r) => within(r).queryAllByRole("button").length)).toEqual([1, 0, 1]);
});
