// @vitest-environment jsdom
// ADR-110 decision 7: the Publish screen's structured schedule — chosen, explained in words with the
// next five runs before saving (the Conduit's words, from the executor's arithmetic), saved with its
// zone, read back as the same choice, paused and resumed, and its runs listed beneath.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { PublishScreen } from "./PublishScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PUBLISHED = {
  recipe_id: "r1", version: 2, status: "published", label: "Carrier B intake", connector_profile: "generic-csv",
  source_location: "/exports/a.csv", handling: {}, legal_basis: "RIPA s22", owning_unit: "unit-1", created_by: "a1",
  created_at: "2026-10-10T09:00:00Z", git_path: "recipes/r1.yaml", pipeline: null, unmapped_fields: [],
  ready_for_profile: true, schedule_cron: "0 6 * * *", schedule_timezone: "Europe/London", schedule_owner: "approver-1",
  schedule_paused: false, schedule_paused_reason: null,
} as unknown as StudioRecipeDraft;  // prettier-ignore

const NEXT = ["2026-06-08T06:30:00Z", "2026-06-09T06:30:00Z", "2026-06-10T06:30:00Z", "2026-06-11T06:30:00Z", "2026-06-12T06:30:00Z"];
const RUN = { run_id: "x", trigger: "schedule", slot: "2026-06-02T05:00:00Z", started_at: "2026-06-02T05:00:01Z",
  finished_at: null, outcome: "refused", run_as: "approver-1", withheld: false, rows_read: null,
  failure: "the schedule's owner, approver-1, can no longer sign in" };  // prettier-ignore

function serve(draft: StudioRecipeDraft = PUBLISHED, runs: unknown[] = [RUN]) {
  const sent: { method: string; path: string; body: unknown }[] = [];
  let current = draft;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      sent.push({ method: init?.method ?? "GET", path, body });
      const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200 });
      if (path === "/v1/ingest/schedule-preview") {
        if ((body as { cron: string }).cron === "*/5 * * * *")
          return new Response(JSON.stringify({ error: "schedule_refused", detail: "'*/5 * * * *' would run more often than every 15 minutes" }), { status: 422 });
        return ok({ words: "every weekday at 07:30 (Europe/London)", next_runs: NEXT });
      }
      if (path.endsWith("/schedule/pause")) return ok((current = { ...current, schedule_paused: true, schedule_paused_reason: "paused by approver-1" }));
      if (path.endsWith("/schedule/resume")) return ok((current = { ...current, schedule_paused: false, schedule_paused_reason: null }));
      if (path.endsWith("/runs")) return ok(runs);
      if (path.endsWith("/schedule")) return ok((current = { ...current, ...(body as object) }));
      return ok(current);
    }),
  );
  return sent;
}

function place() {
  render(<PublishScreen apiBaseUrl="http://x" bearerToken="t" recipeId="r1" investigationId="c1" onBack={() => {}} />);
}

describe("the structured schedule", () => {
  it("reads an existing daily schedule back as Every day at its time", async () => {
    serve();
    place();
    expect(((await screen.findByLabelText("How often")) as HTMLSelectElement).value).toBe("daily");
    await waitFor(() => expect((screen.getByLabelText("Time") as HTMLInputElement).value).toBe("06:00"));
  });

  it("explains a chosen schedule in words with its next five runs, then saves it with its zone", async () => {
    const sent = serve();
    place();
    fireEvent.change(await screen.findByLabelText("How often"), { target: { value: "weekdays" } });
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "07:30" } });
    const preview = await screen.findByRole("status", { name: "Schedule preview" });
    expect(within(preview).getByText("Runs every weekday at 07:30 (Europe/London).")).toBeTruthy();
    expect(within(preview).getAllByRole("listitem")).toHaveLength(5);
    expect(sent.at(-1)?.body).toEqual({ cron: "30 7 * * 1-5", timezone: "Europe/London" });
    fireEvent.click(screen.getByRole("button", { name: "Update schedule" }));
    await waitFor(() =>
      expect(sent.find((s) => s.method === "PATCH")?.body).toEqual({
        schedule_cron: "30 7 * * 1-5", schedule_watch: null, schedule_timezone: "Europe/London",
      }),
    );  // prettier-ignore
  });

  it("says, in the Conduit's words, a schedule it could not keep", async () => {
    serve();
    place();
    fireEvent.change(await screen.findByLabelText("How often"), { target: { value: "cron" } });
    fireEvent.change(screen.getByLabelText("Cron expression"), { target: { value: "*/5 * * * *" } });
    expect((await screen.findByRole("alert")).textContent).toContain("more often than every 15 minutes");
  });

  it("pauses and resumes the schedule, saying why it is paused", async () => {
    const sent = serve();
    place();
    fireEvent.click(await screen.findByRole("button", { name: "Pause schedule" }));
    expect(await screen.findByText("Paused — paused by approver-1.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Resume schedule" }));
    await waitFor(() => expect(sent.some((s) => s.path.endsWith("/schedule/resume"))).toBe(true));
  });

  it("lists the recipe's runs, a refused one with why", async () => {
    serve();
    place();
    const runs = await screen.findByRole("list", { name: "Runs of this recipe" });
    expect(within(runs).getByText(/Refused: the schedule's owner, approver-1, can no longer sign in/)).toBeTruthy();
  });

  // ADR-110 decision 5, Amendment 4: the folder watch.
  const WATCHABLE = { ...PUBLISHED, schedule_cron: null, dataset_id: "carrier-b" } as unknown as StudioRecipeDraft;

  it("watches the recipe's own dataset folder for a filename pattern, and saves it", async () => {
    const sent = serve(WATCHABLE);
    place();
    const field = await screen.findByLabelText("Run when a file arrives — filename pattern");
    expect(screen.getByText(/in the carrier-b folder/)).toBeTruthy();
    fireEvent.change(field, { target: { value: "*.csv" } });
    fireEvent.click(screen.getByRole("button", { name: "Update schedule" }));
    await waitFor(() =>
      expect(sent.find((s) => s.method === "PATCH")?.body).toEqual({
        schedule_cron: null, schedule_watch: "*.csv", schedule_timezone: null,
      }),
    );  // prettier-ignore
    // A watch alone is a schedule that can be paused.
    expect(await screen.findByRole("button", { name: "Pause schedule" })).toBeTruthy();
  });

  it("says a recipe in no dataset has no folder to watch", async () => {
    serve({ ...WATCHABLE, dataset_id: null } as unknown as StudioRecipeDraft);
    place();
    const field = (await screen.findByLabelText("Run when a file arrives — filename pattern")) as HTMLInputElement;
    expect(field.disabled).toBe(true);
    expect(screen.getByText(/belongs to no dataset, so it has no folder to watch/)).toBeTruthy();
  });

  it("names the file a watched run took", async () => {
    const watched = { ...RUN, run_id: "w", trigger: "watch", slot: null, outcome: "succeeded", file: "2026-06-02.csv",
      rows_read: 4, nodes_created: 2, nodes_referenced: 0, rows_rejected: 0, failure: null };  // prettier-ignore
    serve(WATCHABLE, [watched]);
    place();
    const runs = await screen.findByRole("list", { name: "Runs of this recipe" });
    expect(within(runs).getByText(/watch, 2026-06-02\.csv: Succeeded: 4 rows read/)).toBeTruthy();
  });
});
