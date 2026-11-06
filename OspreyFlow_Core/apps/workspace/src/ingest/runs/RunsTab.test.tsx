// @vitest-environment jsdom
// ADR-140 decision 16 (redesign phase 2): the Runs tab. What would fail if each part were wrong: a day
// with held rows drawn as succeeded; a cell that opens no report; the revert command shown to someone
// without `revert_loads`, or offered as a button (ADR-127 Amendment 9: the Conduit is stopped for it);
// held rows unreachable from the run that held them; Run now not reaching the run controls.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ScheduleRunView, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { RunsTab, revertCommand } from "./RunsTab";

vi.mock("../publish/PublishScreen", () => ({
  PublishScreen: ({ recipeId, mode }: { recipeId: string; mode: string }) => <p>{`controls ${recipeId} ${mode}`}</p>,
}));
vi.mock("../../alerts/HeldRowsPanel", () => ({ HeldRowsPanel: () => <p>held-rows-panel</p> }));

afterEach(cleanup);

const PIPELINES = [
  { recipe_id: "r1", version: 1, status: "published", label: "PIN calls", owning_unit: "u", created_by: "e",
    created_at: "", ready_for_profile: true, schedule_watch: "*.csv" },
  { recipe_id: "r2", version: 4, status: "draft", label: "Intel reports", owning_unit: "u", created_by: "e",
    created_at: "", ready_for_profile: false },
] as StudioRecipeDraft[];  // prettier-ignore

const RUNS: Record<string, ScheduleRunView[]> = {
  r1: [
    { run_id: "a", trigger: "manual", started_at: "2026-11-04T09:00:00Z", outcome: "succeeded", run_as: "osprey-demo-engineer",
      rows_read: 200, nodes_created: 0, nodes_referenced: 400, rows_rejected: 0, rows_held: 0, load_id: "01LOADA" },
    { run_id: "b", trigger: "watch", file: "pin-2.csv", started_at: "2026-11-03T09:00:00Z", outcome: "succeeded",
      run_as: "osprey-demo-engineer", rows_read: 10, nodes_created: 2, nodes_referenced: 0, rows_rejected: 0, rows_held: 2,
      load_id: "01LOADB" },
  ],
};  // prettier-ignore

function open(canRevert: boolean) {
  render(
    <RunsTab
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="inv-1"
      datasetId="prison-intelligence"
      datasetName="Prison Intelligence Dataset"
      pipelines={PIPELINES}
      runs={RUNS}
      level="editor"
      canRevert={canRevert}
      username="osprey-demo-engineer"
      onChanged={() => undefined}
      today={new Date("2026-11-05T12:00:00Z")}
    />,
  );
}

describe("the Runs tab", () => {
  it("draws one row per deployed pipeline and a cell per day, in words", () => {
    open(false);
    const grid = screen.getByRole("region", { name: "Runs by day" });
    expect(within(grid).getAllByRole("row")).toHaveLength(2);
    expect(within(grid).queryByText(/Intel reports/)).toBeNull();
    expect(screen.getByRole("button", { name: "PIN calls, 4 Nov: succeeded" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "PIN calls, 3 Nov: needs a person" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "PIN calls, 5 Nov: scheduled, not yet run" })).toBeTruthy();
  });

  it("opens a day's run report from its cell, and the held rows from a run that held some", () => {
    open(false);
    fireEvent.click(screen.getByRole("button", { name: "PIN calls, 3 Nov: needs a person" }));
    const report = screen.getByRole("region", { name: "Run report" });
    expect(within(report).getByText(/watch, pin-2.csv, as osprey-demo-engineer: Succeeded: 10 rows read, 2 created, 0 referenced, 0 rejected, 2 held/)).toBeTruthy();
    fireEvent.click(within(report).getByRole("button", { name: "Open held rows" }));
    expect(screen.getByText("held-rows-panel")).toBeTruthy();
  });

  it("shows the revert as the operator's command to a holder of revert_loads, and to no one else", () => {
    open(true);
    fireEvent.click(screen.getByRole("button", { name: "PIN calls, 4 Nov: succeeded" }));
    expect(
      screen.getByText(
        "python -m scripts.seed_internal prison-intelligence --revert-load 01LOADA --reverted-by osprey-demo-engineer --stop-api",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Revert/ })).toBeNull();
    cleanup();
    open(false);
    fireEvent.click(screen.getByRole("button", { name: "PIN calls, 4 Nov: succeeded" }));
    expect(screen.queryByText(/--revert-load/)).toBeNull();
  });

  it("opens a chosen pipeline's run and schedule controls", () => {
    open(false);
    fireEvent.change(screen.getByRole("combobox", { name: "Pipeline to run or schedule" }), { target: { value: "r1" } });
    fireEvent.click(screen.getByRole("button", { name: "Run now or schedule" }));
    expect(screen.getByText("controls r1 operate")).toBeTruthy();
  });

  it("names a revert's pack for a dataset outside the Prison Intelligence one, and the person when unknown", () => {
    expect(revertCommand("carrier-b", "01X", null)).toBe(
      "python -m scripts.seed_internal ledger --revert-load 01X --reverted-by <your username> --stop-api",
    );
  });
});
