// @vitest-environment jsdom
// ADR-110 decision 8: the Admin area's Schedules and runs. Each schedule in words with its case, owner,
// next run and last outcome; a run's counts said withheld, never shown, when the Conduit withholds
// them; pause and resume; a recipe's history; a refusal said.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const RUN = {
  run_id: "r1", trigger: "schedule", slot: "2026-06-02T05:00:00Z", started_at: "2026-06-02T05:00:01Z",
  finished_at: "2026-06-02T05:00:09Z", outcome: "succeeded", run_as: "approver-1", withheld: false,
  rows_read: 40, nodes_created: 12, nodes_referenced: 3, edges_created: 20, rows_rejected: 1, rows_held: 0,
  load_id: "l1", failure: null,
};  // prettier-ignore
const WITHHELD = { ...RUN, run_id: "r2", outcome: "failed", withheld: true, rows_read: null, nodes_created: null,
  nodes_referenced: null, edges_created: null, rows_rejected: null, rows_held: null, load_id: null };  // prettier-ignore
// A slot that did not run carries no counts, as the ledger records it.
const MISSED = { ...RUN, run_id: "r0", outcome: "missed", rows_read: null, nodes_created: null, nodes_referenced: null,
  edges_created: null, rows_rejected: null, rows_held: null, load_id: null, failure: "the deployment was not running then" };  // prettier-ignore
const SCHEDULE = {
  recipe_id: "feed", label: "Daily custody export", case_id: "case-1", cron: "0 6 * * 1-5", timezone: "Europe/London",
  schedule: "every weekday at 06:00 (Europe/London)", owner: "approver-1", next_run: "2026-06-03T05:00:00Z",
  paused: false, paused_reason: null, flagged: false, last_run: RUN,
};  // prettier-ignore
const SECRET = { ...SCHEDULE, recipe_id: "secret", label: "Informant returns", last_run: WITHHELD };

function serve(handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push(`${init?.method ?? "GET"} ${path}`);
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "schedules") return json(200, [SCHEDULE, SECRET]);
      if (path === "schedules/feed/pause")
        return json(200, { ...SCHEDULE, paused: true, paused_reason: "paused by admin-1", next_run: null });
      if (path === "schedules/feed/resume") return json(200, SCHEDULE);
      if (path === "schedules/feed/runs") return json(200, [RUN, MISSED]);
      return json(404, {});
    }),
  );
  return sent;
}

function place(rights: string[]) {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
}

describe("Schedules and runs", () => {
  it("is a tab only for an account holding operate_schedules", async () => {
    serve();
    place(["administer_system"]);
    expect(screen.queryByRole("tab", { name: "Schedules and runs" })).toBeNull();
    cleanup();
    serve();
    place(["operate_schedules"]);
    expect(await screen.findByRole("table", { name: "Scheduled recipes" })).toBeTruthy();
  });

  it("shows each schedule in words with its case, owner and last outcome", async () => {
    serve();
    place(["operate_schedules"]);
    const row = (await screen.findByText("Daily custody export")).closest("tr")!;
    const cells = within(row);
    expect(cells.getByText("every weekday at 06:00 (Europe/London)")).toBeTruthy();
    expect(cells.getByText("case-1")).toBeTruthy();
    expect(cells.getByText("approver-1")).toBeTruthy();
    expect(cells.getByText(/Succeeded: 40 rows read, 12 created, 3 referenced, 1 rejected/)).toBeTruthy();
  });

  it("says counts are withheld, and shows none, where the Conduit withholds them", async () => {
    serve();
    place(["operate_schedules"]);
    const row = (await screen.findByText("Informant returns")).closest("tr")!;
    expect(within(row).getByText(/Failed: counts withheld — the source is above your clearance/)).toBeTruthy();
    expect(within(row).queryByText(/rows read/)).toBeNull();
  });

  it("pauses and resumes a schedule, saying why it is paused", async () => {
    const sent = serve();
    place(["operate_schedules"]);
    fireEvent.click(await screen.findByRole("button", { name: "Pause Daily custody export" }));
    expect(await screen.findByText("paused by admin-1")).toBeTruthy();
    expect(sent).toContain("POST schedules/feed/pause");
    fireEvent.click(screen.getByRole("button", { name: "Resume Daily custody export" }));
    await waitFor(() => expect(sent).toContain("POST schedules/feed/resume"));
    expect(await screen.findByRole("button", { name: "Pause Daily custody export" })).toBeTruthy();
  });

  it("shows a recipe's runs, with a slot that did not run and why", async () => {
    serve();
    place(["operate_schedules"]);
    fireEvent.click(await screen.findByRole("button", { name: "Show runs of Daily custody export" }));
    const history = await screen.findByRole("list", { name: "Runs of Daily custody export" });
    expect(within(history).getByText(/Missed: the deployment was not running then/)).toBeTruthy();
  });

  it("says when nothing is scheduled, and says a refusal", async () => {
    serve((path) => (path === "schedules" ? json(200, []) : null));
    place(["operate_schedules"]);
    expect(await screen.findByText("No recipe is scheduled.")).toBeTruthy();
    cleanup();
    serve((path) => (path === "schedules" ? json(403, {}) : null));
    place(["operate_schedules"]);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Your account does not hold the right for this.");
  });
});
