// @vitest-environment jsdom
// The Studio as ADR-108 phase B ships it: a pipelines home, the canvas as the one editing surface,
// stage panels per node, and the save gate's words shown — never swallowed.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PipelineGraph, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
// The rehosted stage editors have their own tests and pull canvas machinery jsdom cannot host;
// here they are stubs — this file tests the Studio shell, the canvas and the panels.
vi.mock("../ConnectScreen", () => ({ ConnectScreen: () => <p>connect-screen</p> }));
vi.mock("../ProfileScreen", () => ({ ProfileScreen: () => <p>profile-screen</p> }));
vi.mock("../map/MapScreen", () => ({ MapScreen: () => <p>map-screen</p> }));
vi.mock("../verify/VerifyScreen", () => ({ VerifyScreen: () => <p>verify-screen</p> }));
vi.mock("../publish/PublishScreen", () => ({ PublishScreen: () => <p>publish-screen</p> }));
vi.mock("./NodePreview", () => ({ NodePreview: () => <p>node-preview</p> }));

import { PipelineStudio } from "./PipelineStudio";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CHAIN: PipelineGraph = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    { id: "source", kind: "source", label: "Carrier B", config: {} },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: {} },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

function draft(pipeline: PipelineGraph | null = CHAIN): StudioRecipeDraft {
  return {
    recipe_id: "r1",
    version: 1,
    status: "draft",
    label: "Carrier B intake",
    connector_profile: "generic-csv",
    source_location: null,
    handling: {},
    legal_basis: null,
    owning_unit: "unit-1",
    created_by: "a1",
    created_at: "2026-10-10T09:00:00Z",
    pipeline,
    unmapped_fields: [],
    ready_for_profile: false,
  } as unknown as StudioRecipeDraft;
}

const PACKS = [
  { name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] },
  { name: "fibo", label: "Financial fraud and AML (FIBO)", entity_types: ["Account"], edge_types: ["BENEFICIAL_OWNER_OF"] },
];

function serve(overrides: { putStatus?: number; putBody?: unknown; registry?: StudioRecipeDraft[] } = {}) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url: String(url), body });
      const path = String(url);
      const json = (status: number, payload: unknown) =>
        ({ ok: status < 400, status, json: async () => payload }) as Response;
      if (path.endsWith("/v1/ingest/packs")) return json(200, PACKS);
      if (path.endsWith("/pipeline") && method === "PUT") {
        if (overrides.putStatus) return json(overrides.putStatus, overrides.putBody);
        return json(200, draft(body as PipelineGraph));
      }
      if (/\/ingest\/recipes\/r1$/.test(path) && method === "GET") return json(200, draft());
      if (/\/ingest\/recipes\/r1$/.test(path) && method === "PATCH") return json(200, draft());
      if (path.endsWith("/ingest/recipes") && method === "POST") return json(201, draft(null));
      if (path.endsWith("/ingest/recipe-registry")) return json(200, overrides.registry ?? [draft()]);
      return json(404, { error: "not_found" });
    }),
  );
  return calls;
}

function mount() {
  render(<PipelineStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
}

async function openPipeline() {
  fireEvent.click(await screen.findByRole("button", { name: "Open Carrier B intake" }));
  await screen.findByRole("group", { name: "Pipeline" });
}

describe("PipelineStudio", () => {
  it("lists the pipelines and opens one onto the canvas", async () => {
    serve();
    mount();
    expect(await screen.findByText(/Carrier B intake/)).toBeTruthy();
    await openPipeline();
    expect(screen.getAllByRole("button", { name: /: / })).toHaveLength(5);
  });

  it("keeps a published pipeline listed, and opens a recipe from before pipelines at Publish", async () => {
    // Found live, 11 October 2026: the home listed drafts only, so a pipeline vanished on publish —
    // nobody could run it again, schedule it or release its held rows — and a recipe the ontology
    // flagged could not be reached to republish.
    const published = { ...draft(), recipe_id: "r2", label: "Onboarding applications", status: "published" };
    const flagged = { ...draft(null), recipe_id: "r3", label: "Carrier B subscribers", status: "flagged" };
    const superseded = { ...draft(), recipe_id: "r4", label: "Old intake", status: "superseded" };
    serve({ registry: [published, flagged, superseded] as StudioRecipeDraft[] });
    mount();
    expect(await screen.findByText(/Onboarding applications/)).toBeTruthy();
    expect(screen.getByText(/· deployed/)).toBeTruthy();
    expect(screen.queryByText(/Old intake/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open Carrier B subscribers" }));
    expect(await screen.findByText("publish-screen")).toBeTruthy();
  });

  it("names a new pipeline and lands on its canvas", async () => {
    const calls = serve();
    mount();
    fireEvent.change(await screen.findByLabelText("Pipeline name"), { target: { value: "Fresh" } });
    fireEvent.click(screen.getByRole("button", { name: "New pipeline" }));
    await screen.findByRole("group", { name: "Pipeline" });
    const made = calls.find((c) => c.method === "POST");
    expect((made?.body as { label: string }).label).toBe("Fresh");
  });

  it("adds a whole source branch and saves the pipeline", async () => {
    const calls = serve();
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "+ Source" }));
    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put).toBeTruthy();
      expect((put!.body as PipelineGraph).nodes).toHaveLength(9);
    });
  });

  it("shows the save gate's words when the graph is refused", async () => {
    serve({ putStatus: 422, putBody: { error: "pipeline_invalid", problems: ["the pipeline holds a cycle; data must flow one way"] } });
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "+ Source" }));
    expect(await screen.findByText(/holds a cycle/)).toBeTruthy();
  });

  it("the domain panel offers the packs and applies the chosen one", async () => {
    const calls = serve();
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "Domain model: Domain model" }));
    const panel = await screen.findByRole("radiogroup", { name: "Domain pack" });
    expect(within(panel).getByText(/Adds Account/)).toBeTruthy();
    fireEvent.click(within(panel).getByRole("radio", { name: /FIBO/ }));
    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put).toBeTruthy();
      const nodes = (put!.body as PipelineGraph).nodes!;
      expect(nodes.find((n) => n.kind === "domain_model")!.config!.pack).toBe("fibo");
    });
  });

  it("the first source's panel opens the Connect gate whole (file, marking, legal basis)", async () => {
    serve();
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "Source: Carrier B" }));
    fireEvent.click(await screen.findByRole("button", { name: "The draft's own settings" }));
    expect(await screen.findByText("connect-screen")).toBeTruthy();
  });

  it("the extract panel declares library, media and where findings go", async () => {
    const calls = serve();
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "+ Extract" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Extract: Extract" }));
    fireEvent.change(await screen.findByLabelText("Extraction library"), { target: { value: "spacy" } });
    fireEvent.change(screen.getByLabelText("Findings go to"), { target: { value: "inferred_graph" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply extract settings" }));
    await waitFor(() => {
      const puts = calls.filter((c) => c.method === "PUT");
      const nodes = (puts.at(-1)!.body as PipelineGraph).nodes!;
      const extract = nodes.find((n) => n.kind === "extract")!;
      expect(extract.config).toMatchObject({ library: "spacy", output: "inferred_graph" });
    });
  });

  // --- Phase 6 (ADR-108 Amendment 6, ADR-140 decision 3): the drawer, and the two modes ----------

  it("opens Test, Deploy and the Connect gate in the drawer, with the pipeline still in view", async () => {
    serve();
    mount();
    await openPipeline();
    for (const [press, shown] of [["Test", "verify-screen"], ["Deploy", "publish-screen"]] as const) {
      fireEvent.click(screen.getByRole("button", { name: press }));
      expect(await screen.findByText(shown)).toBeTruthy();
      expect(screen.getByRole("group", { name: "Pipeline" })).toBeTruthy();
      expect(within(screen.getByRole("complementary", { name: "Drawer" })).getByText(shown)).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("button", { name: "Source: Carrier B" }));
    fireEvent.click(await screen.findByRole("button", { name: "The draft's own settings" }));
    expect(await screen.findByText("connect-screen")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Steps" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close the drawer" }));
    expect(screen.queryByText("connect-screen")).toBeNull();
  });

  it("previews a node from its drawer", async () => {
    serve();
    mount();
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "Map: Map" }));
    fireEvent.click(await screen.findByRole("button", { name: "Preview" }));
    expect(await screen.findByText("node-preview")).toBeTruthy();
  });

  it("starts in guided mode: the numbered steps, and a picture of the canvas with nothing to press", async () => {
    window.localStorage.clear();
    serve();
    mount();
    await openPipeline();
    expect(screen.getByRole("button", { name: "Guided" }).getAttribute("aria-pressed")).toBe("true");
    const steps = within(screen.getByRole("list", { name: "Steps" })).getAllByRole("button");
    expect(steps.map((b) => b.textContent)).toEqual([
      "Domain model: Domain model", "Source: Carrier B", "Profile: Profile", "Map: Map", "Load: Load",
    ]);  // prettier-ignore
    expect(within(screen.getByRole("group", { name: "Pipeline" })).queryAllByRole("button")).toHaveLength(0);
  });

  it("switches to expert mode, where the canvas is the editor, and keeps the choice for the person", async () => {
    window.localStorage.clear();
    serve();
    render(<PipelineStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" username="engineer-1" />);
    await openPipeline();
    fireEvent.click(screen.getByRole("button", { name: "Expert" }));
    expect(screen.queryByRole("list", { name: "Steps" })).toBeNull();
    expect(within(screen.getByRole("group", { name: "Pipeline" })).getAllByRole("button")).toHaveLength(5);
    cleanup();
    render(<PipelineStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" username="engineer-1" />);
    await openPipeline();
    expect(screen.getByRole("button", { name: "Expert" }).getAttribute("aria-pressed")).toBe("true");
    window.localStorage.clear();
  });

  it("shows an expert step in guided mode, labelled and read-only", async () => {
    window.localStorage.clear();
    const withSql = {
      nodes: [...CHAIN.nodes!, { id: "sql", kind: "sql_transform", label: "Visits per week", config: { sql: "SELECT 1" } }],
      edges: [...CHAIN.edges!, { source: "profile", target: "sql" }],
    } as unknown as PipelineGraph;
    serve({ registry: [draft(withSql)] });
    vi.mocked(fetch).mockImplementation((async (url: string) =>
      ({ ok: true, status: 200, json: async () => (String(url).endsWith("/ingest/recipe-registry") ? [draft(withSql)] : draft(withSql)) }) as Response) as never);
    mount();
    await openPipeline();
    expect(screen.getByText("Expert step, read-only here")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "SQL transform: Visits per week" }));
    const step = await screen.findByRole("region", { name: "Expert step" });
    expect(within(step).getByText("SELECT 1")).toBeTruthy();
    expect(within(step).queryAllByRole("button")).toHaveLength(0);
    expect(within(step).queryAllByRole("textbox")).toHaveLength(0);
  });
});

