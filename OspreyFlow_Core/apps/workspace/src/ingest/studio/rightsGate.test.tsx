// @vitest-environment jsdom
// ADR-145 Amendment 4 decision 12 (L1.8): every Studio action a person can't take says why and who can,
// never only greyed out. What would fail if it were wrong:
// - an action needing a right offered to someone without it, so their press sends a write the route then
//   refuses — `pressing every button with no rights sends no write`, per surface;
// - an action greyed out with no words, or words naming a role id or a person — `refused` below checks
//   each listed action is focusable, `aria-disabled`, and described by "You need <right>; the <roles>…",
//   with no `_` (a role or right id) in it;
// - a holder of the right told they can't — `a holder of every right is offered every action`.
// Shown red with each gate taken out (`process/lanes/studio-b/l1.8/red-studio-tips.txt`).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ScheduleRunView, SourceTable, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import BY_ROLE from "../../shell/placesByRole.json";
import { ChecksScreen } from "../checks/ChecksScreen";
import { PipelineStudio } from "../dag/PipelineStudio";
import { IngestStudio } from "../IngestStudio";
import { PublishScreen } from "../publish/PublishScreen";
import { RunsTab } from "../runs/RunsTab";
import { SourcePage } from "../sources/SourcePage";
import { VerifyScreen } from "../verify/VerifyScreen";
import { RightButton, StudioRights } from "./rightsGate";
import { SourcesTab } from "./SourcesTab";

vi.mock("../../alerts/HeldRowsPanel", () => ({ HeldRowsPanel: () => <p>held-rows-panel</p> }));
// The map editor and the graph canvas draw with WebGL, which jsdom has not; none of these screens is under test here.
vi.mock("../map/MapScreen", () => ({ MapScreen: () => null }));
vi.mock("../ProfileScreen", () => ({ ProfileScreen: () => null }));
vi.mock("../ConnectScreen", () => ({ ConnectScreen: () => null }));
vi.mock("../dag/NodePreview", () => ({ NodePreview: () => null }));
vi.mock("../../canvas/GlassCanvas", () => ({ GlassCanvas: () => null }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const NONE: ReadonlySet<string> = new Set();
const EVERY: ReadonlySet<string> = new Set(
  Object.values((BY_ROLE as { roles: Record<string, { rights?: string[] }> }).roles).flatMap((r) => r.rights ?? []),
);

type Call = { path: string; method: string };

/** A write is anything but a read: every non-GET, bar the previews the Studio reads by POST. */
const isWrite = (c: Call) => c.method !== "GET" && !/(-preview|preview-graph)$/.test(c.path);

const json = (status: number, payload: unknown) => ({ ok: status < 400, status, json: async () => payload }) as Response;

function serve(answers: (path: string, method: string) => unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      const method = init?.method ?? "GET";
      calls.push({ path, method });
      const answer = answers(path, method);
      return answer === undefined ? json(404, { detail: "not_found" }) : json(200, answer);
    }),
  );
  return calls;
}

function as(rights: ReadonlySet<string> | null, node: ReactNode) {
  return render(<StudioRights.Provider value={rights}>{node}</StudioRights.Provider>);
}

/** The action is offered to the keyboard and refused in words: the right by its name, who holds it. */
async function refused(name: string | RegExp, right: string) {
  const button = await screen.findByRole("button", { name });
  expect(button.getAttribute("aria-disabled")).toBe("true");
  expect(button.hasAttribute("disabled")).toBe(false); // focusable, so its tip is reachable (rule 13)
  const tip = document.getElementById(button.getAttribute("aria-describedby") ?? "")?.textContent ?? "";
  expect(tip).toMatch(new RegExp(`^You need ${right}; the .+ roles? ha(s|ve) it\\. Ask an administrator`));
  expect(tip).not.toMatch(/_/);
  return button;
}

/** Every button on the screen pressed, and no write sent. */
function pressEverything(calls: Call[]) {
  for (const button of screen.getAllByRole("button")) fireEvent.click(button);
  expect(calls.filter(isWrite)).toEqual([]);
}

const DRAFT = {
  recipe_id: "r1", version: 3, status: "draft", label: "PIN calls", connector_profile: "generic-csv",
  source_location: "/in/a.csv", handling: {}, legal_basis: "Synthetic", owning_unit: "u", created_by: "e",
  created_at: "2026-11-01T09:00:00Z", pipeline: null, unmapped_fields: [], ready_for_profile: true,
  dataset_id: "ds-a", schedule_cron: "0 6 * * *",
} as unknown as StudioRecipeDraft;  // prettier-ignore
const PUBLISHED = { ...DRAFT, status: "published" } as StudioRecipeDraft;

const recipe = (draft: StudioRecipeDraft) => (path: string) => (/\/ingest\/recipes\/r1$/.test(path) ? draft : undefined);

describe("a Studio action the person can't take", () => {
  it("says why and who can, and does nothing when pressed", () => {
    const pressed = vi.fn();
    as(NONE, <RightButton right="review_promotions" onClick={pressed}>Review</RightButton>);
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(pressed).not.toHaveBeenCalled();
    expect(screen.getByText("You need Review promotions; the Data Engineer role has it. Ask an administrator to give it to you.")).toBeTruthy();
  });

  it("is offered as before while the person's rights are not known (the route answers for itself)", () => {
    const pressed = vi.fn();
    as(null, <RightButton right="review_promotions" onClick={pressed}>Review</RightButton>);
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("on Deploy: deploying, and deploying and running", async () => {
    const calls = serve(recipe(DRAFT));
    as(NONE, <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />);
    await refused("Deploy as v3", "Publish pipelines");
    await refused("Deploy and run now", "Publish pipelines");
    pressEverything(calls);
  });

  it("on a deployed pipeline's controls: its schedule, pausing it, running it and reopening it", async () => {
    const calls = serve(recipe(PUBLISHED));
    as(NONE, <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
    await refused("Update schedule", "Schedule pipelines");
    await refused("Pause schedule", "Schedule pipelines");
    await refused("Run now", "Run pipelines");
    pressEverything(calls);
    cleanup();
    const again = serve(recipe(PUBLISHED));
    as(NONE, <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />);
    await refused("Reopen for editing", "Edit pipelines");
    pressEverything(again);
  });

  it("on the schedule, for someone who may schedule but not deploy (its routes take both)", async () => {
    const calls = serve(recipe(PUBLISHED));
    as(new Set(["schedule_pipelines", "run_pipelines"]),
      <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);  // prettier-ignore
    await refused("Update schedule", "Publish pipelines");
    await refused("Pause schedule", "Publish pipelines");
    expect((await screen.findByRole("button", { name: "Run now" })).hasAttribute("aria-disabled")).toBe(false);
    for (const name of ["Update schedule", "Pause schedule"]) fireEvent.click(screen.getByRole("button", { name }));
    expect(calls.filter(isWrite)).toEqual([]);
  });

  it("on Test and on the load rules", async () => {
    const calls = serve((path) => (path.endsWith("/v1/ontology") ? { entity_types: [], edge_types: [] } : recipe(DRAFT)(path)));
    as(NONE, <VerifyScreen apiBaseUrl="http://api" investigationId="inv-1" bearerToken="t" recipeId="r1" onBack={() => undefined} />);
    await refused("Run the test", "Verify pipelines");
    pressEverything(calls);
    cleanup();
    const view = { recipe_id: "r1", chosen: false, checks: [], available: [] };
    const checks = serve((path) => (path.endsWith("/checks") ? view : undefined));
    as(NONE, <ChecksScreen apiBaseUrl="http://api" investigationId="inv-1" bearerToken="t" recipeId="r1" onBack={() => undefined} />);
    await refused("Save the load rules", "Edit pipelines");
    pressEverything(checks);
  });

  it("on Pipelines: a new pipeline", async () => {
    const calls = serve((path) => (path.endsWith("/recipe-registry") ? [] : undefined));
    as(NONE, <PipelineStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    fireEvent.change(screen.getByRole("textbox", { name: "Pipeline name" }), { target: { value: "PIN calls" } });
    await refused("New pipeline", "Edit pipelines");
    pressEverything(calls);
  });

  it("on Sources: the tab, registering, adding files, importing a list, and a source's own actions", async () => {
    const source: SourceTable = {
      id: "s1", dataset_id: "ds-a", connection_id: "c1", name: "Visits", location: "visits", connector_profile: "generic-csv",
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" }, legal_basis: "Synthetic",
      refresh: { trigger: "watch", pattern: "v-*.csv", mode: "snapshot", dropped_rows: "withdraw", owner: "e", paused: false },
      read: { kind: "sql", table: "public.visits", columns: [] }, version: 1, created_by: "e", created_at: "2026-11-06T09:00:00Z",
    } as SourceTable;  // prettier-ignore
    const calls = serve((path) => {
      if (path.endsWith("/sources")) return [source];
      if (path.endsWith("/screening-subscriptions")) return { lists: [], subscribed: [] };
      if (path.endsWith("/reference-lists/offered")) return [];
      if (path.endsWith("/lineage")) return [];
      return undefined;
    });
    as(NONE, <SourcesTab apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" datasetId="ds-a" onOpenPipelines={() => undefined} />);
    // The tab's own line, beside each button's tip.
    const lines = await screen.findAllByText(/^You need Add ingest files; the Analyst and Data Engineer roles have it/);
    expect(lines.some((el) => el.tagName === "P")).toBe(true);
    await refused("Register a source", "Add ingest files");
    await refused("Add files", "Add ingest files");
    await refused("Import a list", "Load screening lists");
    await refused("Import rows for one of this dataset's lists", "Add ingest files");
    expect(calls.filter(isWrite)).toEqual([]);
    fireEvent.click(await screen.findByRole("button", { name: /Open source Visits/ }));
    await refused("Edit governance", "Edit pipelines");
    await refused("Pause the refresh", "Schedule pipelines");
    await refused("Refresh now", "Add ingest files");
    pressEverything(calls);
  });

  it("on a pipeline's source: uploading a file", async () => {
    const { ConnectScreen } = await vi.importActual<typeof import("../ConnectScreen")>("../ConnectScreen");
    const calls = serve((path) => {
      if (path === "/v1/ingest/connectors") return [{ id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true }];
      if (path === "/v1/handling-scheme") return { name: "uk", classification: ["OFFICIAL"], handling_codes: {} };
      if (path.endsWith("/ingest/recipes")) return [];
      if (path.endsWith("/ingest/source-files")) return { root: "/in", files: [] };
      return undefined;
    });
    as(NONE, <ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="t" />);
    await refused("Choose file…", "Add ingest files");
    fireEvent.click(screen.getByRole("button", { name: "Choose file…" }));
    expect(calls.filter(isWrite)).toEqual([]);
  });

  it("on a paused source: resuming its refresh", async () => {
    const paused = {
      id: "s1", dataset_id: "ds-a", connection_id: "files", name: "Cells", location: "/in/ds-a/cells.csv",
      connector_profile: "generic-csv", handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      legal_basis: "Synthetic", version: 1, created_by: "e", created_at: "2026-11-06T09:00:00Z",
      refresh: { trigger: "watch", pattern: "cells-*.csv", mode: "snapshot", dropped_rows: "withdraw", owner: "e", paused: true },
    } as SourceTable;  // prettier-ignore
    const calls = serve((path) => (path.endsWith("/lineage") ? [] : undefined));
    as(NONE,
      <SourcePage api={{ apiBaseUrl: "http://api", bearerToken: "t" }} datasetId="ds-a" source={paused} scheme={null}
        onBack={() => undefined} onChanged={() => undefined} onOpenInPipeline={() => undefined} />,
    );  // prettier-ignore
    await refused("Resume the refresh", "Schedule pipelines");
    pressEverything(calls);
  });

  it("on Runs: a day's held rows, and a load's revert", async () => {
    const runs: Record<string, ScheduleRunView[]> = {
      r1: [{ run_id: "a", trigger: "manual", started_at: "2026-11-04T09:00:00Z", outcome: "succeeded", run_as: "e",
        rows_read: 2, nodes_created: 2, nodes_referenced: 0, rows_rejected: 0, rows_held: 1, load_id: "01LOADA" }],
    };  // prettier-ignore
    const calls = serve(() => undefined);
    as(NONE,
      <RunsTab apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" datasetId="ds-a" datasetName="Visits"
        pipelines={[PUBLISHED]} runs={runs} level="editor" canRevert={false} username="e" onChanged={() => undefined}
        today={new Date("2026-11-05T12:00:00Z")} />,
    );  // prettier-ignore
    // Run now or schedule only opens the controls, each of which says why not on its own.
    expect(screen.getByRole("button", { name: "Run now or schedule" }).hasAttribute("aria-disabled")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /^PIN calls, 4 Nov: / }));
    const report = screen.getByRole("region", { name: "Run report" });
    expect(within(report).getByText("You need Revert loads; the Administrator and Data Engineer roles have it. Ask an administrator to give you one.")).toBeTruthy();
    await refused("Open held rows", "Read held rows");
    fireEvent.click(screen.getByRole("button", { name: "Open held rows" }));
    expect(screen.queryByText("held-rows-panel")).toBeNull();
    expect(calls.filter(isWrite)).toEqual([]);
  });

  it("on Model: proposed link types, for someone who cannot accept types", async () => {
    const cases = [{ id: "inv-1", name: "Visits case", level: "editor", created_at: "", created_by: "e", domains: [],
      datasets: ["Visits"], dataset_ids: ["ds-a"] }];  // prettier-ignore
    const calls = serve((path) => (path.endsWith("/v1/investigations") ? cases : []));
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" onOpenCase={() => undefined} rights={NONE} />);
    fireEvent.click(screen.getByRole("tab", { name: "1 Model" }));
    const region = await screen.findByRole("region", { name: "Proposed link types" });
    expect(within(region).getByText(/^You need Accept types; the Data Engineer role has it/)).toBeTruthy();
    expect(calls.some((c) => c.path.includes("/model/proposals"))).toBe(false);
  });

  it("opens *Roles, teams and Authors* from the Studio, and back", async () => {
    serve(() => []);
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" onOpenCase={() => undefined} rights={NONE} />);
    fireEvent.click(screen.getByRole("button", { name: "Roles, teams and Authors" }));
    expect(screen.getByRole("heading", { name: "Roles, teams and Authors" })).toBeTruthy();
    const back = screen.getByRole("button", { name: "← Back to the Ingest Studio" });
    await waitFor(() => expect(document.activeElement).toBe(back));
    fireEvent.click(back);
    expect(screen.getByRole("tab", { name: "3 Pipelines" })).toBeTruthy();
  });

  it("keeps what was typed in the Studio while the help page is read", async () => {
    serve((path) => (path.endsWith("/recipe-registry") ? [] : []));
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" onOpenCase={() => undefined} rights={EVERY} />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Pipeline name" }), { target: { value: "Half-typed" } });
    fireEvent.click(screen.getByRole("button", { name: "Roles, teams and Authors" }));
    fireEvent.click(screen.getByRole("button", { name: "← Back to the Ingest Studio" }));
    expect((screen.getByRole("textbox", { name: "Pipeline name" }) as HTMLInputElement).value).toBe("Half-typed");
  });
});

describe("a holder of every right", () => {
  it("is offered every action", async () => {
    serve(recipe(DRAFT));
    as(EVERY, <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />);
    const deploy = await screen.findByRole("button", { name: "Deploy as v3" });
    expect(deploy.hasAttribute("aria-disabled")).toBe(false);
    expect(document.querySelector("[data-why-not]")).toBeNull();
  });
});
