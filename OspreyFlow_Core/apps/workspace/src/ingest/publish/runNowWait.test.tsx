// @vitest-environment jsdom
// Step 9d finding 7: the capture kit waited for a run by the words "Succeeded:", "Failed" or
// "refused" anywhere on the Publish screen — and the screen's own runs list already holds an older
// run's "Succeeded:" before the new run answers, so the wait ended while the new run was still going.
// The kit now waits on the new run's own request (`live/run-wait.ts`), which this holds to the
// requests the Publish screen really sends: its run-now POST, never the runs list's GET.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { isRunNowRequest, runNowOutcome } from "../../../live/run-wait";
import { PublishScreen } from "./PublishScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PUBLISHED = {
  recipe_id: "r1", version: 2, status: "published", label: "Visit bookings", connector_profile: "generic-csv",
  source_location: "/exports/a.csv", handling: {}, legal_basis: "RIPA s22", owning_unit: "unit-1", created_by: "a1",
  created_at: "2026-10-10T09:00:00Z", git_path: "recipes/r1.yaml", pipeline: null, unmapped_fields: [],
  ready_for_profile: true, schedule_cron: null, schedule_timezone: null, schedule_owner: null,
  schedule_paused: false, schedule_paused_reason: null,
} as unknown as StudioRecipeDraft;  // prettier-ignore

/** An earlier rehearsal's run of the same recipe, succeeded. */
const OLDER = { run_id: "older", trigger: "manual", slot: null, started_at: "2026-11-01T09:00:00Z",
  finished_at: "2026-11-01T09:01:00Z", outcome: "succeeded", run_as: "engineer", withheld: false, rows_read: 12,
  nodes_created: 3, nodes_referenced: 9, edges_created: 4, rows_rejected: 0, failure: null };  // prettier-ignore

const REPORT = { load_id: "load-new", recipe_id: "r1", recipe_version: 2, rows_read: 14, nodes_created: 5,
  nodes_referenced: 9, edges_created: 6, rejections: [], rows_held: 0, rule_notes: [], withheld: false };  // prettier-ignore

function serve() {
  const sent: { method: string; url: string }[] = [];
  let answer: (r: Response) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      sent.push({ method: init?.method ?? "GET", url });
      const path = new URL(url).pathname;
      if (path.endsWith("/run")) return new Promise<Response>((resolve) => (answer = resolve));
      if (path.endsWith("/runs")) return Promise.resolve(new Response(JSON.stringify([OLDER]), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify(PUBLISHED), { status: 200 }));
    }),
  );
  return { sent, answer: (r: Response) => answer(r) };
}

describe("the capture kit's wait for a run it started", () => {
  it("is the run-now request alone: the screen shows an older Succeeded while the new run is going", async () => {
    const { sent } = serve();
    render(<PublishScreen apiBaseUrl="http://glass/api" bearerToken="t" recipeId="r1" investigationId="c1" onBack={() => {}} mode="operate" />);
    const runs = await screen.findByRole("list", { name: "Runs of this recipe" });
    fireEvent.click(await screen.findByRole("button", { name: "Run now" }));
    // The defect: the words the old wait looked for are on screen, from the older run, before the
    // new run has answered at all.
    expect(within(runs).getByText(/Succeeded:/)).toBeTruthy();
    const posts = sent.filter((s) => isRunNowRequest(s.method, s.url));
    expect(posts).toEqual([{ method: "POST", url: "http://glass/api/v1/investigations/c1/ingest/recipes/r1/run" }]);
    // The runs list's own read (which holds the older run) and the draft's are never taken for it.
    const others = sent.filter((s) => !isRunNowRequest(s.method, s.url)).map((s) => new URL(s.url).pathname);
    expect(others).toContain("/api/v1/investigations/c1/ingest/recipes/r1/runs");
  });

  it("says the new run's own outcome from its own answer", () => {
    expect(runNowOutcome(200, REPORT)).toBe("Succeeded (load load-new): 14 rows read, 5 created, 9 referenced, 0 rejected, 0 held");
    expect(runNowOutcome(200, { ...REPORT, withheld: true })).toBe("Succeeded (load load-new): counts withheld");
    expect(runNowOutcome(422, { error: "load_refused", detail: "the source file is not there" })).toBe(
      "Refused (422): the source file is not there",
    );
    expect(runNowOutcome(500, null)).toBe("Failed (500)");
  });

  it("never takes a GET, or another recipe action's POST, for the run", () => {
    const base = "http://glass/api/v1/investigations/c1/ingest/recipes/r1";
    expect(isRunNowRequest("GET", `${base}/run`)).toBe(false);
    expect(isRunNowRequest("GET", `${base}/runs`)).toBe(false);
    expect(isRunNowRequest("POST", `${base}/runs`)).toBe(false);
    expect(isRunNowRequest("POST", `${base}/versions`)).toBe(false);
    expect(isRunNowRequest("POST", `${base}/run?x=1`)).toBe(true);
  });
});
