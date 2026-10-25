// A keyboard-only walkthrough of the pipeline Studio (ADR-108 phase B, rule 13): create and open
// a pipeline, grow it, choose a domain pack, declare an extract, remove a node, and reach the map
// editor — no `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { PIPELINE_STUDIO_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PIPELINE_STUDIO_ACTIONS";

const CHAIN = {
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

const PACKS = [
  { name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] },
  { name: "stix", label: "Cyber threat analytics (STIX 2.1)", entity_types: ["ThreatActor"], edge_types: ["TARGETS"] },
];

// ADR-127 Amendment 2: Map's own reads — the source's columns, the ontology it may map to.
const PROFILE = {
  rows_sampled: 1,
  sample_is_whole_source: true,
  values_masked: false,
  columns: [
    { name: "marking", sample_size: 1, null_count: 0, distinct_count: 1, inferred_type: "string", type_confidence: 1 },
    { name: "id", sample_size: 1, null_count: 0, distinct_count: 1, inferred_type: "string", type_confidence: 1 },
  ],
  anomalies: [],
};

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle", properties: [] }],
  edge_types: [],
};

function draft(pipeline: unknown, handling: Record<string, unknown> = {}) {
  return {
    recipe_id: "r1",
    version: 1,
    status: "draft",
    label: "Carrier B intake",
    connector_profile: "generic-csv",
    source_location: null,
    handling,
    legal_basis: null,
    owning_unit: "unit-1",
    created_by: "a1",
    created_at: "2026-10-10T09:00:00Z",
    pipeline,
    unmapped_fields: [],
    ready_for_profile: false,
  };
}

async function serve(page: Page, declared: Record<string, unknown> = {}) {
  const puts: unknown[] = [];
  const patches: { handling: Record<string, unknown> }[] = [];
  const templates: { row_template: { entities: { handling?: Record<string, unknown> }[] } }[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.endsWith("/v1/ingest/packs")) return json(200, PACKS);
    if (url.endsWith("/v1/ingest/connectors"))
      return json(200, [
        { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
      ]);
    if (url.endsWith("/v1/handling-scheme"))
      return json(200, {
        name: "uk-le",
        classification: ["PUBLIC", "OFFICIAL"],
        handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
      });
    if (url.endsWith("/ingest/recipes/r1/profile")) return json(200, PROFILE);
    if (url.endsWith("/v1/ontology")) return json(200, ONTOLOGY);
    if (url.endsWith("/v1/ingest/transforms")) return json(200, []);
    if (url.endsWith("/ingest/recipes/r1/row-template") && method === "PUT") {
      const sent = request.postDataJSON();
      templates.push(sent);
      return json(200, { ...draft(CHAIN, declared), row_template: sent.row_template });
    }
    if (url.endsWith("/ingest/source-files")) return json(200, { root: "/r", files: [] });
    if (url.endsWith("/pipeline") && method === "PUT") {
      const sent = request.postDataJSON();
      puts.push(sent);
      return json(200, draft(sent));
    }
    if (url.endsWith("/ingest/recipes/r1") && method === "GET") return json(200, draft(CHAIN, declared));
    if (url.endsWith("/ingest/recipes/r1") && method === "PATCH") {
      const sent = request.postDataJSON();
      patches.push(sent);
      return json(200, draft(CHAIN, sent.handling));
    }
    if (url.endsWith("/ingest/recipes") && method === "POST") return json(201, draft(null));
    if (url.endsWith("/ingest/recipes") && method === "GET") return json(200, [draft(CHAIN, declared)]);
    // The pipelines home lists the registry (every status but superseded), not drafts only.
    if (url.endsWith("/ingest/recipe-registry") && method === "GET") return json(200, [draft(CHAIN)]);
    return json(404, {});
  });
  await page.goto("/keyboard/pipeline-studio-harness.html");
  return Object.assign(puts, { patches, templates });
}

async function openPipeline(page: Page) {
  const open = page.getByRole("button", { name: "Open Carrier B intake" });
  await open.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
}

test("a pipeline is named and created by keyboard", async ({ page }) => {
  await serve(page);
  await page.getByLabel("Pipeline name").focus();
  await page.keyboard.type("Fresh");
  await page.getByRole("button", { name: "New pipeline" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
  registerCovered(REGISTRY, "create-a-pipeline-by-keyboard");
});

test("a listed pipeline opens by keyboard", async ({ page }) => {
  await serve(page);
  await openPipeline(page);
  registerCovered(REGISTRY, "open-a-pipeline-by-keyboard");
});

test("a source branch is added by keyboard and the save goes out", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "+ Source" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  expect((puts[0] as { nodes: unknown[] }).nodes).toHaveLength(9);
  registerCovered(REGISTRY, "add-a-source-branch-by-keyboard");
});

test("a domain pack is chosen by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Domain model: Domain model" }).focus();
  await page.keyboard.press("Enter");
  const stix = page.getByRole("radio", { name: /STIX/ });
  await stix.focus();
  await page.keyboard.press(" ");
  await expect.poll(() => puts.length).toBe(1);
  const nodes = (puts[0] as { nodes: { kind: string; config: { pack?: string } }[] }).nodes;
  expect(nodes.find((n) => n.kind === "domain_model")!.config.pack).toBe("stix");
  registerCovered(REGISTRY, "choose-a-domain-pack-by-keyboard");
});

test("extract settings are declared by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "+ Extract" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  await page.getByRole("button", { name: "Extract: Extract" }).focus();
  await page.keyboard.press("Enter");
  const library = page.getByLabel("Extraction library");
  await library.focus();
  await library.selectOption("spacy");
  // Apply is disabled until the first save has been answered, which `puts` (counting requests
  // sent) does not wait for: pressed while disabled it did nothing (20 October 2026).
  const apply = page.getByRole("button", { name: "Apply extract settings" });
  await expect(apply).toBeEnabled();
  await apply.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(2);
  const nodes = (puts[1] as { nodes: { kind: string; config: { library?: string } }[] }).nodes;
  expect(nodes.find((n) => n.kind === "extract")!.config.library).toBe("spacy");
  registerCovered(REGISTRY, "apply-extract-settings-by-keyboard");
});

test("a node is removed by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Remove selected" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  expect((puts[0] as { nodes: unknown[] }).nodes).toHaveLength(4);
  registerCovered(REGISTRY, "remove-a-node-by-keyboard");
});

test("the source settings open from the first source's node by keyboard", async ({ page }) => {
  await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Source: Carrier B" }).focus();
  await page.keyboard.press("Enter");
  const open = page.getByRole("button", { name: "Open source settings" });
  await open.focus();
  await page.keyboard.press("Enter");
  // The Connect gate whole: the file, the marking, the legal basis — proven by its own unit
  // tests; reaching it from the node is this test's.
  await expect(page.getByRole("button", { name: "Choose file…" })).toBeVisible();
  await page.getByRole("button", { name: "Back to the pipeline" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
  registerCovered(REGISTRY, "open-the-source-settings-by-keyboard");
});

async function openSourceSettings(page: Page) {
  await openPipeline(page);
  await page.getByRole("button", { name: "Source: Carrier B" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Open source settings" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Choose file…" })).toBeVisible();
}

test("a unit the source's rows may name is added in Connect by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page);
  await openSourceSettings(page);
  await page.getByLabel("Unit name").focus();
  await page.keyboard.type("unit-9");
  await page.keyboard.press("Enter");
  await expect(page.getByText("unit-9", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.patches.length).toBe(1);
  expect(served.patches[0]!.handling.units).toEqual(["unit-9"]);
  registerCovered(REGISTRY, "add-a-source-unit-by-keyboard");
});

test("a column that carries the marking is declared in Connect by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page);
  await openSourceSettings(page);
  await page.getByLabel("Column carrying Classification").focus();
  await page.keyboard.type("marking");
  await page.getByRole("button", { name: "Save", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.patches.length).toBe(1);
  expect(served.patches[0]!.handling.handling_columns).toEqual({ classification: "marking" });
  registerCovered(REGISTRY, "declare-a-marking-column-by-keyboard");
});

test("an element's classification is bound to the declared column in Map by keyboard, and the saved template holds it", async ({ page }) => {
  const served = await serve(page, { classification: "OFFICIAL", handling_columns: { classification: "marking" } });
  await openPipeline(page);
  await page.getByRole("button", { name: "Map: Map" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Open map editor" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "+ entity" }).focus();
  await page.keyboard.press("Enter");
  // The element leaves a declared part unbound, and says so before the save does.
  await expect(page.getByRole("status").filter({ hasText: "does not bind Classification" })).toBeVisible();
  await page.getByLabel("Override handling for this element").focus();
  await page.keyboard.press(" ");
  const part = page.getByLabel("Classification for this element");
  await part.focus();
  // Key presses only: typing the option's first letters picks it in a closed native select.
  await page.keyboard.type("From");
  await expect(part.locator("option:checked")).toHaveText("From column marking");
  await expect(page.getByRole("status").filter({ hasText: "does not bind" })).toBeHidden();
  await page.getByRole("button", { name: "Save draft" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[0]!.handling).toEqual({ classification: { field: "marking" } });
  registerCovered(REGISTRY, "bind-a-handling-part-to-a-column-by-keyboard");
});

test("the map editor opens from its node by keyboard", async ({ page }) => {
  await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Map: Map" }).focus();
  await page.keyboard.press("Enter");
  const open = page.getByRole("button", { name: "Open map editor" });
  await open.focus();
  await page.keyboard.press("Enter");
  // The map editor is the existing MapScreen, proven by its own specs; reaching it is this test's.
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeHidden();
  registerCovered(REGISTRY, "open-the-map-editor-by-keyboard");
});

test("every registered pipeline-studio action has its own proving test case above", () => {
  assertAllCovered("PIPELINE_STUDIO_ACTIONS", PIPELINE_STUDIO_ACTIONS);
});
