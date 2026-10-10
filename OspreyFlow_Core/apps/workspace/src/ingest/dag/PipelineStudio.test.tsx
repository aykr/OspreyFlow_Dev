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

function serve(overrides: { putStatus?: number; putBody?: unknown } = {}) {
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
      if (path.endsWith("/ingest/recipes") && method === "GET") return json(200, [draft()]);
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
    fireEvent.click(await screen.findByRole("button", { name: "Open source settings" }));
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
});
