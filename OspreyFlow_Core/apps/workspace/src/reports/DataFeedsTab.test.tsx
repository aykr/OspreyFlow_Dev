// @vitest-environment jsdom
// ADR-110 decision 9: the Data feeds tab — each pipeline feeding the case, its schedule in words, next
// run and last outcome, read-only; counts said withheld where the Conduit withheld them.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DataFeedsTab } from "./DataFeedsTab";
import { json, serve } from "./reportsTestKit";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const RUN = {
  run_id: "r1", trigger: "schedule", slot: "2026-06-02T05:00:00Z", started_at: "2026-06-02T05:00:01Z",
  finished_at: "2026-06-02T05:00:09Z", outcome: "succeeded", run_as: "approver-1", withheld: false,
  rows_read: 40, nodes_created: 12, nodes_referenced: 3, edges_created: 20, rows_rejected: 0, rows_held: 0,
  load_id: "l1", failure: null,
};  // prettier-ignore
const FEEDS = [
  { recipe_id: "daily", label: "Custody export", schedule: "every day at 06:00 (Europe/London)",
    next_run: "2026-06-03T05:00:00Z", paused: false, flagged: false, last_run: RUN },
  { recipe_id: "secret", label: "Informant returns", schedule: "every day at 07:00 (Europe/London)",
    next_run: "2026-06-03T06:00:00Z", paused: false, flagged: false,
    last_run: { ...RUN, run_id: "r2", withheld: true, rows_read: null, nodes_created: null, nodes_referenced: null,
                rows_rejected: null, rows_held: null, load_id: null } },
  { recipe_id: "hand", label: "Seizure list", schedule: null, next_run: null, paused: false, flagged: false, last_run: null },
];  // prettier-ignore

const API = { apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" };

describe("the Data feeds tab", () => {
  it("shows each feed's schedule in words, next run and last outcome", async () => {
    const calls = serve((c) => (c.path === "data-feeds" ? json(200, FEEDS) : null));
    render(<DataFeedsTab api={API} />);
    const row = (await screen.findByText("Custody export")).closest("tr")!;
    expect(within(row).getByText("every day at 06:00 (Europe/London)")).toBeTruthy();
    expect(within(row).getByText(/Succeeded: 40 rows read/)).toBeTruthy();
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET data-feeds"]);
  });

  it("says counts are withheld rather than showing any", async () => {
    serve((c) => (c.path === "data-feeds" ? json(200, FEEDS) : null));
    render(<DataFeedsTab api={API} />);
    const row = (await screen.findByText("Informant returns")).closest("tr")!;
    expect(within(row).getByText(/counts withheld — some of what it loaded is above your clearance or restricted to another unit/)).toBeTruthy();
    expect(within(row).queryByText(/rows read/)).toBeNull();
  });

  it("says a feed is run by hand, and when it has not run", async () => {
    serve((c) => (c.path === "data-feeds" ? json(200, FEEDS) : null));
    render(<DataFeedsTab api={API} />);
    const row = (await screen.findByText("Seizure list")).closest("tr")!;
    expect(within(row).getByText("Run by hand")).toBeTruthy();
    expect(within(row).getByText("Not run yet")).toBeTruthy();
  });

  it("says when nothing feeds the case, and says a refusal", async () => {
    serve(() => json(200, []));
    render(<DataFeedsTab api={API} />);
    expect(await screen.findByText("No pipeline loads into this case's data yet.")).toBeTruthy();
    cleanup();
    serve(() => json(403, {}));
    render(<DataFeedsTab api={API} />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have the right to read its data feeds in this case.");
  });
});
