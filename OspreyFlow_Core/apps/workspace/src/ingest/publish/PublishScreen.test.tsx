// @vitest-environment jsdom
// ADR-108 phase C, rule 12's question answered: if the run route's pipeline answer were rendered
// as a plain load report — branches, stage counts and refusal words dropped on the floor — this
// is the test that fails. A stage that could not run must be readable here, in words (rule 2).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { PublishScreen } from "./PublishScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PUBLISHED = {
  recipe_id: "r1",
  version: 2,
  status: "published",
  label: "Carrier B intake",
  connector_profile: "generic-csv",
  source_location: "/exports/a.csv",
  handling: {},
  legal_basis: "RIPA s22",
  owning_unit: "unit-1",
  created_by: "a1",
  created_at: "2026-10-10T09:00:00Z",
  git_path: "recipes/r1.yaml",
  pipeline: null,
  unmapped_fields: [],
  ready_for_profile: true,
} as unknown as StudioRecipeDraft;

const PIPELINE_RUN = {
  load_id: "L1",
  recipe_id: "r1",
  recipe_version: 2,
  branches: [
    {
      source_id: "source",
      source_label: "Export A",
      report: { load_id: "L1:source", recipe_id: "r1", recipe_version: 2, rows_read: 3, nodes_created: 2 },
    },
  ],
  extracts: [
    {
      node_id: "extract",
      library: "spacy",
      output: "review_queue",
      documents_read: 1,
      candidates_queued: 4,
      refusals: ["the extraction library 'whisper' is not available in this deployment"],
    },
  ],
  enriches: [
    { node_id: "enrich", geocoder: "local_gazetteer", locations_considered: 2, matched_local: 1, unmatched: 1 },
  ],
  rows_read: 3,
  nodes_created: 2,
  nodes_referenced: 0,
  edges_created: 0,
  rejections: [],
};

function serve(run: unknown = PIPELINE_RUN) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      const json = (status: number, payload: unknown) =>
        ({ ok: status < 400, status, json: async () => payload }) as Response;
      if (path.endsWith("/run") && method === "POST") return json(200, run);
      if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, PUBLISHED);
      return json(404, { error: "not_found" });
    }),
  );
}

describe("PublishScreen", () => {
  it("renders a pipeline run per branch and per stage, refusals in words", async () => {
    serve();
    render(
      <PublishScreen
        apiBaseUrl="http://api"
        bearerToken="t"
        recipeId="r1"
        investigationId="inv-1"
        onBack={() => undefined} mode="operate"
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
    const stages = await screen.findByRole("list", { name: "Pipeline stages" });
    expect(stages.textContent).toContain("Source “Export A”: 3 rows read");
    expect(stages.textContent).toContain("Extract (spacy): 1 documents read, 4 findings queued for review");
    expect(stages.textContent).toContain("refused: the extraction library 'whisper' is not available");
    expect(stages.textContent).toContain("Enrich (local_gazetteer): 2 places considered, 1 matched locally");
  });

  it("says what the case's rules did, and how many rows wait for review", async () => {
    // Found by the spec survey, 11 October 2026: the run report carried `rows_held` and
    // `rule_notes` (ADR-109 ruling 1) but the Studio drew neither, so a fully held load read as a
    // load that simply made nothing.
    serve({ ...PIPELINE_RUN, nodes_created: 0, rows_held: 2,
            rule_notes: ["Rule “Onboarding screen” could not judge 2 row(s): held for review."] });  // prettier-ignore
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
    fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
    expect(await screen.findByText("Rows held for review: 2 — a reviewer releases or rejects them on the Runs tab or in Monitoring › Held rows")).toBeTruthy();
    const rules = screen.getByRole("list", { name: "What the case's rules did" });
    expect(rules.textContent).toContain("could not judge 2 row(s)");
  });

  // Rule 3, ADR-127 Amendment 25 (ADR-124 option A′): a run whose rows include a marking the
  // loader may not view comes back `withheld`, with every count zero. Drawn as zeros it would read
  // as a load that made nothing; it says it withholds instead.
  it("says counts are withheld, with the reason, and draws no zero, for a withheld run", async () => {
    serve({ load_id: "L9", recipe_id: "r1", recipe_version: 2, withheld: true, rows_read: 0,
            nodes_created: 0, nodes_referenced: 0, edges_created: 0, rejections: [], rows_held: 0,
            rule_notes: [] });  // prettier-ignore
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
    fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
    expect(await screen.findByText(/Counts withheld — .*above your clearance.*another unit/)).toBeTruthy();
    expect(screen.getByText("Load id: L9")).toBeTruthy();
    expect(screen.queryByText(/Rows read/)).toBeNull();
    expect(screen.queryByText(/Nodes created/)).toBeNull();
    expect(screen.queryByText(/Edges created/)).toBeNull();
  });

  // Build order step 30 (the owner, 4 November 2026; spec 09 §5): Run reads exactly the file Verify
  // checked. The Run panel no longer takes another file, and the route's refusal when the file has
  // changed since Verify is shown in its own words. Red if the free-text file field comes back or
  // the refusal is swallowed.
  it("offers no other file to run on, and says why a changed source is refused", async () => {
    const said =
      "reports.csv has changed since Test checked it. Nothing was loaded. Run Test again, then run.";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const json = (status: number, payload: unknown) =>
          ({ ok: status < 400, status, json: async () => payload }) as Response;
        if (String(url).endsWith("/run") && init?.method === "POST") {
          expect(JSON.parse(String(init.body))).toEqual({ source_location: null });
          return json(409, { error: "source_changed_since_verify", detail: said });
        }
        if (/\/ingest\/recipes\/r1$/.test(String(url))) return json(200, PUBLISHED);
        return json(404, { error: "not_found" });
      }),
    );
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
    const run = await screen.findByRole("button", { name: /Run now/ });
    expect(screen.queryByRole("textbox", { name: /Source file/ })).toBeNull();
    expect(screen.getByText(/Runs on the file Test checked/)).toBeTruthy();
    fireEvent.click(run);
    expect(await screen.findByText(said)).toBeTruthy();
  });

  it("withholds a withheld pipeline run's branches too", async () => {
    serve({ ...PIPELINE_RUN, withheld: true, rows_read: 0, nodes_created: 0, branches: [], extracts: [], enriches: [] });
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
    fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
    expect(await screen.findByText(/Counts withheld/)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Pipeline stages" })).toBeNull();
    expect(screen.queryByText(/Rows read/)).toBeNull();
  });
});

// ADR-140 decision 14 (redesign phase 2): Deploy commits a version and neither runs nor schedules it.
// Red if the deploy sends the schedule editor's choice, if Deploy runs, or if the run controls stay.
describe("Deploy", () => {
  const DRAFT = { ...PUBLISHED, status: "draft", version: 3, schedule_cron: "0 6 * * *", schedule_timezone: "Europe/London" };

  function serveDeploy() {
    const calls: { path: string; method: string; body: unknown }[] = [];
    let current: unknown = DRAFT;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url);
        const method = init?.method ?? "GET";
        calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : null });
        const json = (status: number, payload: unknown) =>
          ({ ok: status < 400, status, json: async () => payload }) as Response;
        if (path.endsWith("/publish") && method === "POST") {
          current = { ...DRAFT, status: "published" };
          return json(200, current);
        }
        if (path.endsWith("/run") && method === "POST") return json(200, { ...PIPELINE_RUN, load_id: "L7" });
        if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, current);
        return json(404, { error: "not_found" });
      }),
    );
    return calls;
  }

  it("deploys as the draft's version, keeping the schedule the draft holds, and does not run", async () => {
    const calls = serveDeploy();
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />);
    expect(screen.queryByRole("button", { name: /Run now/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Update schedule/ })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Deploy as v3" }));
    await screen.findByText("Deployed");
    const publish = calls.find((c) => c.path.endsWith("/publish"));
    expect(publish?.body).toEqual({ schedule_cron: "0 6 * * *", schedule_watch: null, schedule_timezone: "Europe/London" });
    expect(calls.some((c) => c.path.endsWith("/run"))).toBe(false);
    expect(screen.getByText(/run, and\s+its schedule and folder watch are set, on the Runs tab/)).toBeTruthy();
  });

  it("deploys and runs at once when asked to", async () => {
    const calls = serveDeploy();
    render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deploy and run now" }));
    expect(await screen.findByText("Load id: L7")).toBeTruthy();
    const order = calls.filter((c) => c.method === "POST").map((c) => c.path.split("/").pop());
    expect(order).toEqual(["publish", "run"]);
  });
});
