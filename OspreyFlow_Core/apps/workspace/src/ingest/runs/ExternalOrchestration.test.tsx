// @vitest-environment jsdom
// The Runs tab's external orchestration (ADR-141 decisions 6, 9 and 11). What would fail if each part
// were wrong: a quota bar past its limit, or drawn with no quota; Mark owned externally offered over a
// schedule of the pipeline's own, or without Schedule pipelines; a DAG with a secret in it, without the
// orchestrator's run id as the key, or not pinning the version chosen.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { airflowDag, ExternalOrchestration, ORCHESTRATION_WORDS } from "./ExternalOrchestration";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CALLS = { recipe_id: "r-calls", version: 3, status: "published", label: "Wing phone calls", owning_unit: "u",
  created_by: "e", created_at: "", ready_for_profile: true } as StudioRecipeDraft;  // prettier-ignore
const SCHEDULED = { ...CALLS, recipe_id: "r-sched", label: "Scheduled", schedule_cron: "0 6 * * *" } as StudioRecipeDraft;

function serve(owned: unknown = null, quota: unknown = { quota: { scope: "dataset", key: "ds", runs_per_day: 4 }, runs_today: 3, used: false }) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/quota")) return new Response(JSON.stringify(quota));
      if (url.endsWith("/owned-externally") && init?.method === "PUT") return new Response(init.body as string);
      if (url.endsWith("/owned-externally")) return new Response(JSON.stringify(owned));
      return new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

function open(deployed = [CALLS], canSchedule = true) {
  render(
    <ExternalOrchestration apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" datasetId="ds" deployed={deployed} canSchedule={canSchedule} />,
  );
}

describe("ExternalOrchestration", () => {
  it("draws today's runs against the dataset's quota", async () => {
    serve();
    open();
    expect(await screen.findByText("3 of 4 runs a day")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "Runs today against the dataset's quota" }).getAttribute("value")).toBe("3");
  });

  it("tells a reader not given the count only whether the quota is used, with no bar", async () => {
    serve(null, { quota: { scope: "dataset", key: "ds", runs_per_day: 4 }, runs_today: null, used: true });
    open();
    expect(await screen.findByText(ORCHESTRATION_WORDS.quotaUsed(4))).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.queryByText(/^\d+ of 4 runs a day$/)).toBeNull();
  });

  it("says a quota is set and not used, without a count", async () => {
    serve(null, { quota: { scope: "dataset", key: "ds", runs_per_day: 1 }, runs_today: null, used: false });
    open();
    expect(await screen.findByText("This dataset's quota is 1 run a day; it is not used today.")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("says when no quota is set, and draws no bar", async () => {
    serve(null, { quota: null, runs_today: 2, used: false });
    open();
    expect(await screen.findByText(ORCHESTRATION_WORDS.noQuota)).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("marks a pipeline owned externally by the client named, and says who each run acts as", async () => {
    const calls = serve();
    open();
    fireEvent.change(await screen.findByLabelText("The orchestrator's client"), { target: { value: "syn-airflow" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark owned externally" }));
    expect((await screen.findByRole("status")).textContent).toContain("only syn-airflow may trigger it, and each run acts as you");
    const put = calls.find((c) => c.init?.method === "PUT");
    expect(put?.url).toBe("http://api/v1/investigations/inv-1/ingest/recipes/r-calls/owned-externally");
    expect(JSON.parse(String(put?.init?.body))).toEqual({ client_id: "syn-airflow" });
  });

  it("is not offered over a schedule of the pipeline's own, nor without Schedule pipelines", async () => {
    serve();
    open([SCHEDULED]);
    fireEvent.change(await screen.findByLabelText("The orchestrator's client"), { target: { value: "x" } });
    expect((screen.getByRole("button", { name: "Mark owned externally" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(ORCHESTRATION_WORDS.hasSchedule)).toBeTruthy();
    cleanup();
    serve();
    open([CALLS], false);
    expect(screen.getByText(ORCHESTRATION_WORDS.noRight)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark owned externally" })).toBeNull();
  });

  it("shows who it is owned by, and takes it back", async () => {
    const calls = serve({ client_id: "syn-airflow" });
    open();
    expect(await screen.findByText("Owned externally: only syn-airflow may trigger it.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Take it back" }));
    await screen.findByText("Wing phone calls is no longer owned externally.");
    expect(calls.some((c) => c.init?.method === "DELETE")).toBe(true);
  });
});

describe("airflowDag", () => {
  it("runs the CLI keyed by Airflow's own run id, pins what is chosen, and holds no secret", () => {
    const latest = airflowDag("ds", CALLS, "latest");
    expect(latest).toContain("ospreyflow run ds r-calls --version latest --external-run-id {{ dag.dag_id }}:{{ run_id }} --wait --fail-on held");
    expect(airflowDag("ds", CALLS, 3)).toContain("--version 3 ");
    expect(latest).not.toMatch(/OSPREY_CLIENT_SECRET\s*=|password|token=/i);
    expect(latest).toContain('dag_id="ospreyflow_r_calls"');
  });

  it("keeps a label with a line break inside its comment", () => {
    const dag = airflowDag("ds", { ...CALLS, label: "Calls\nimport os; os.system('x')" }, "latest");
    expect(dag.split("\n").filter((l) => l.includes("import os"))).toEqual([
      `# Generated by OspreyFlow's Studio › Runs for "Calls import os; os.system('x')" (ADR-141 decision 9).`,
    ]);
  });
});
