// @vitest-environment jsdom
// Admin › Running › Operations' figures (ADR-141 decisions 3, 4, 6, 7 and 14). What would fail if
// each part were wrong: a withheld count drawn as a number or as 0; an external trigger without its
// service identity or the person it ran as; a quota saved for the wrong scope; a refused save shown
// as a status code.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OperationsRollup } from "../../../../packages/schemas/generated";
import { OPERATIONS_WORDS, OperationsFigures } from "./OperationsFigures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ROLLUP: OperationsRollup = {
  days: 7,
  units: ["unit-1"],
  rows: [
    { day: "2026-11-10", pipeline_id: "p1", pipeline_label: "Visits", unit: "unit-1", trigger: "external", runs: 2,
      succeeded: 1, refused: 1, failed: 0, wall_ms: 4200, rows_read: 120, graph_writes: 30, withheld: false },
    { day: "2026-11-09", pipeline_id: "p2", pipeline_label: "Calls", unit: "unit-1", trigger: "schedule", runs: 1,
      succeeded: 1, refused: 0, failed: 0, wall_ms: 900, rows_read: null, graph_writes: null, withheld: true },
  ],
  scheduler: { skipped: 1, missed: 0, running_now: 0, paused: [],
    refused: [{ reason: "the dataset's quota of 1 run a day is used", count: 1 }] },
  external: [{ run_id: "r1", pipeline_label: "Visits", service_identity: "airflow-prod", ran_as_name: "Sam Rowe",
    started_at: "2026-11-10T09:00:00Z", outcome: "succeeded", wall_ms: 2100, withheld: false }],
  quotas: [{ scope: "dataset", key: "pid", runs_per_day: 1, alert_at_share: 0.8 }],
  alerts: [{ scope: "dataset", key: "pid", day: "2026-11-10", words: "The dataset's runs today reached 80% of its quota of 1 run a day" }],
}; // prettier-ignore

function serve(...answers: { status: number; body: unknown }[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const next = answers.shift() ?? { status: 200, body: ROLLUP };
      return new Response(JSON.stringify(next.body), { status: next.status });
    }),
  );
  return calls;
}

const API = { apiBaseUrl: "http://api", bearerToken: "t" };

describe("OperationsFigures", () => {
  it("rolls the runs up, withholding a count it may not show, never drawing it as a number", async () => {
    serve({ status: 200, body: ROLLUP });
    render(<OperationsFigures api={API} />);
    const table = await screen.findByRole("table", {
      name: "Runs by day, pipeline and trigger",
    });
    const [, visits, calls] = within(table).getAllByRole("row");
    expect(within(visits!).getByText("External")).toBeTruthy();
    expect(within(visits!).getByText("120")).toBeTruthy();
    expect(within(calls!).getAllByText(OPERATIONS_WORDS.withheld)).toHaveLength(
      2,
    );
    expect(within(calls!).queryByText("0")).toBeNull();
  });

  it("names each external trigger's service identity and the person it ran as", async () => {
    serve({ status: 200, body: ROLLUP });
    render(<OperationsFigures api={API} />);
    const table = await screen.findByRole("table", {
      name: "External triggers",
    });
    expect(within(table).getByText("airflow-prod")).toBeTruthy();
    expect(within(table).getByText("Sam Rowe")).toBeTruthy();
    expect(
      screen.getByText(
        "1 refused: the dataset's quota of 1 run a day is used",
      ),
    ).toBeTruthy();
    expect(screen.getByText("2026-11-10: The dataset's runs today reached 80% of its quota of 1 run a day.")).toBeTruthy();
  });

  it("saves a quota for the scope chosen, and reads the figures again", async () => {
    const calls = serve(
      { status: 200, body: ROLLUP },
      {
        status: 200,
        body: {
          scope: "unit",
          key: "unit-1",
          runs_per_day: 5,
          alert_at_share: 0.8,
        },
      },
      { status: 200, body: ROLLUP },
    );
    render(<OperationsFigures api={API} />);
    await screen.findByRole("table", { name: "Run quotas" });
    fireEvent.change(screen.getByLabelText("Quota for"), {
      target: { value: "unit" },
    });
    fireEvent.change(screen.getByLabelText("Unit"), {
      target: { value: "unit-1" },
    });
    fireEvent.change(screen.getByLabelText("Runs a day"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save the run quota" }));
    expect((await screen.findByRole("status")).textContent).toBe(
      "unit-1 may now start 5 runs a day.",
    );
    expect(calls[1]!.url).toBe(
      "http://api/v1/admin/operations/quotas/unit/unit-1",
    );
    expect(JSON.parse(String(calls[1]!.init?.body))).toEqual({
      runs_per_day: 5,
    });
    expect(calls).toHaveLength(3);
  });

  it("says in words why a save was refused", async () => {
    serve(
      { status: 200, body: ROLLUP },
      { status: 403, body: { detail: "x" } },
    );
    render(<OperationsFigures api={API} />);
    await screen.findByRole("table", { name: "Run quotas" });
    fireEvent.change(screen.getByLabelText("Dataset id"), {
      target: { value: "pid" },
    });
    fireEvent.change(screen.getByLabelText("Runs a day"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save the run quota" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      OPERATIONS_WORDS.quotaRight,
    );
  });
});
