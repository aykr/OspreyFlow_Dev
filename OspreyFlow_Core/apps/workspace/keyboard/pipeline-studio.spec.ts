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
    // ADR-127 Amendment 13: a link's time, its end and its text are columns of their own.
    ...["started", "ended", "text"].map((name) => ({
      name, sample_size: 1, null_count: 0, distinct_count: 1, inferred_type: "string", type_confidence: 1,
    })),
    { name: "marking", sample_size: 1, null_count: 0, distinct_count: 1, inferred_type: "string", type_confidence: 1 },
    { name: "id", sample_size: 1, null_count: 0, distinct_count: 1, inferred_type: "string", type_confidence: 1 },
  ],
  anomalies: [],
};

const ONTOLOGY = {
  version: 1,
  entity_types: [
    {
      name: "Endpoint",
      pole_class: "object",
      channel: "ochre",
      shape: "circle",
      properties: [
        { name: "value_normalised", type: "string" },
        { name: "endpoint_kind", type: "string" },
      ],
    },
    { name: "Device", pole_class: "object", channel: "ochre", shape: "circle", properties: [] },
    { name: "Document", pole_class: "object", channel: "violet", shape: "page", properties: [] },
    { name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] },
  ],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct" },
    { name: "PAIRED_WITH", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
  ],
};

function draft(
  pipeline: unknown,
  handling: Record<string, unknown> = {},
  extra: { status?: string; deduplicate?: unknown; rowTemplate?: unknown } = {},
) {
  return {
    ...(extra.rowTemplate === undefined ? {} : { row_template: extra.rowTemplate }),
    recipe_id: "r1",
    version: 1,
    status: extra.status ?? "draft",
    ...(extra.deduplicate === undefined ? {} : { deduplicate: extra.deduplicate }),
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

/** ADR-127 Amendment 10 (B2-5b): what a test of the deduplicate control, Verify or a run report
 * needs the server to say beyond the pipeline's own routes. */
interface ServeOptions {
  /** The draft's saved `deduplicate`. */
  deduplicate?: unknown;
  /** A published recipe with no pipeline opens at Publish, where it is run. */
  published?: boolean;
  /** The draft's saved row template (Map's own state). */
  rowTemplate?: unknown;
  /** What `POST …/verify` and `POST …/run` answer. */
  verify?: unknown;
  run?: unknown;
}

async function serve(page: Page, declared: Record<string, unknown> = {}, options: ServeOptions = {}) {
  const puts: unknown[] = [];
  const patches: { handling: Record<string, unknown>; deduplicate?: { key: Record<string, unknown>[] } }[] = [];
  const templates: {
    row_template: {
      entities: {
        handling?: Record<string, unknown>;
        pole_class?: string;
        type?: string;
        match_on?: string | null;
        on_match?: string;
        content?: { kind: string; field: string };
        when?: Record<string, unknown>;
      }[];
      edges?: {
        type: string;
        from: string;
        to: string;
        temporal?: { at: Record<string, unknown>; valid_to?: Record<string, unknown> };
        content?: { kind: string; field: string };
        handling?: Record<string, unknown>;
      }[];
    };
  }[] = [];
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
    if (url.endsWith("/v1/ingest/transforms"))
      return json(
        200,
        ["datetime", "msisdn", "split"].map((name) => ({ name, arity: 1 })),
      );
    if (url.endsWith("/ingest/recipes/r1/verify") && method === "POST") return json(200, options.verify ?? {});
    if (url.endsWith("/ingest/recipes/r1/run") && method === "POST") return json(200, options.run ?? {});
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
    const status = options.published ? "published" : "draft";
    const shown = (pipeline: unknown) =>
      draft(pipeline, declared, {
        status,
        deduplicate: options.deduplicate,
        rowTemplate: options.rowTemplate,
      });
    if (url.endsWith("/ingest/recipes/r1") && method === "GET") return json(200, shown(options.published ? null : CHAIN));
    if (url.endsWith("/ingest/recipes/r1") && method === "PATCH") {
      const sent = request.postDataJSON();
      patches.push(sent);
      return json(200, draft(CHAIN, sent.handling, { deduplicate: sent.deduplicate }));
    }
    if (url.endsWith("/ingest/recipes") && method === "POST") return json(201, draft(null));
    if (url.endsWith("/ingest/recipes") && method === "GET") return json(200, [shown(CHAIN)]);
    // The pipelines home lists the registry (every status but superseded), not drafts only.
    if (url.endsWith("/ingest/recipe-registry") && method === "GET")
      return json(200, [options.published ? shown(null) : draft(CHAIN)]);
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

// --- ADR-127 Amendment 10 (B2-5b): the deduplicate key, and what a second run says -----------------

async function openConnectWithKey(page: Page, deduplicate: unknown) {
  const served = await serve(page, {}, { deduplicate });
  await openSourceSettings(page);
  await expect(page.getByRole("group", { name: "Skip rows this case has already loaded" })).toBeVisible();
  return served;
}

test("a key column is added to the deduplicate key in Connect by keyboard", async ({ page }) => {
  await openConnectWithKey(page, undefined);
  await page.getByLabel("Key column name").focus();
  await page.keyboard.type("payer");
  await page.keyboard.press("Enter");
  await page.keyboard.type("payee");
  await page.getByRole("button", { name: "Add key column" }).focus();
  await page.keyboard.press("Enter");
  const key = page.getByRole("list", { name: "Key columns" }).getByRole("listitem");
  await expect(key).toHaveCount(2);
  await expect(key.nth(0)).toHaveAttribute("data-column", "payer");
  await expect(key.nth(1)).toHaveAttribute("data-column", "payee");
  registerCovered(REGISTRY, "add-a-deduplicate-key-column-by-keyboard");
});

test("a key column is moved in the deduplicate key by keyboard, and the order is what is saved", async ({ page }) => {
  const served = await openConnectWithKey(page, { key: [{ field: "a" }, { field: "b" }, { field: "c" }] });
  await page.getByRole("button", { name: "Move c up" }).focus();
  await page.keyboard.press("Enter");
  const key = page.getByRole("list", { name: "Key columns" }).getByRole("listitem");
  await expect(key.nth(1)).toHaveAttribute("data-column", "c");
  await page.getByRole("button", { name: "Save", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.patches.length).toBe(1);
  expect(served.patches[0]!.deduplicate!.key.map((part) => part.field)).toEqual(["a", "c", "b"]);
  registerCovered(REGISTRY, "move-a-deduplicate-key-column-by-keyboard");
});

test("a key column is removed from the deduplicate key by keyboard", async ({ page }) => {
  await openConnectWithKey(page, { key: [{ field: "a" }, { field: "b" }] });
  await page.getByRole("button", { name: "Remove a from the key" }).focus();
  await page.keyboard.press("Enter");
  const key = page.getByRole("list", { name: "Key columns" }).getByRole("listitem");
  await expect(key).toHaveCount(1);
  await expect(key.nth(0)).toHaveAttribute("data-column", "b");
  registerCovered(REGISTRY, "remove-a-deduplicate-key-column-by-keyboard");
});

test("the deduplicate key is saved from Connect by keyboard, and the PATCH carries it", async ({ page }) => {
  const served = await openConnectWithKey(page, undefined);
  await page.getByLabel("Key column name").focus();
  await page.keyboard.type("payer");
  await page.keyboard.press("Enter");
  const transform = page.getByLabel("Transform for payer");
  // The catalogue is read after the screen is up: wait for the transform this step picks to be
  // offered, not for a number of options, which grows with the catalogue.
  await expect(transform.locator('option[value="datetime"]')).toHaveCount(1);
  await transform.focus();
  await page.keyboard.type("datetime");
  await page.getByRole("button", { name: "Save", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.patches.length).toBe(1);
  expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "payer", transform: "datetime" }] });
  registerCovered(REGISTRY, "save-the-deduplicate-key-by-keyboard");
});

test("the deduplicate key is cleared in Connect by keyboard, and the PATCH carries an empty key", async ({ page }) => {
  const served = await openConnectWithKey(page, { key: [{ field: "a" }, { field: "b" }] });
  await page.getByRole("button", { name: "Clear the key" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Key columns" })).toBeHidden();
  await page.getByRole("button", { name: "Save", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => served.patches.length).toBe(1);
  expect(served.patches[0]!.deduplicate).toEqual({ key: [] });
  registerCovered(REGISTRY, "clear-the-deduplicate-key-by-keyboard");
});

test("a second run's report says by keyboard how many rows the case already held", async ({ page }) => {
  await serve(page, {}, {
    published: true,
    run: {
      load_id: "L2", recipe_id: "r1", recipe_version: 1, rows_read: 40, rows_deduplicated: 0,
      nodes_created: 0, nodes_referenced: 0, edges_created: 0, rejections: [], rows_already_loaded: 40,
    },
  });
  const open = page.getByRole("button", { name: "Open Carrier B intake" });
  await open.focus();
  await page.keyboard.press("Enter");
  const run = page.getByRole("button", { name: /Run now/ });
  await run.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("40 rows already loaded into this case, skipped")).toBeVisible();
  await expect(page.getByText("Nodes created: 0")).toBeVisible();
  registerCovered(REGISTRY, "read-rows-already-loaded-on-a-run-report-by-keyboard");
});

test("verify says by keyboard how many rows the case already holds", async ({ page }) => {
  await serve(page, {}, {
    verify: {
      rows_read: 40, sample_is_whole_source: true, rows_deduplicated: 0, nodes: [], edges: [],
      entities_by_type: {}, edges_by_type: {}, rejections: [], rows_already_loaded: 40,
    },
  });
  await openPipeline(page);
  await page.getByRole("button", { name: "Verify", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Run verify" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("40 rows already loaded into this case, would be skipped")).toBeVisible();
  registerCovered(REGISTRY, "read-rows-already-loaded-in-verify-by-keyboard");
});

// --- ADR-127 Amendment 13: the links of the row template, by keyboard ---------------------------------

const TWO_ENDPOINTS = [
  { ref: "a", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
  { ref: "b", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
];
const ONE_LINK = {
  entities: TWO_ENDPOINTS,
  edges: [{ type: "COMMUNICATED_WITH", from: "a", to: "b", properties: {} }],
};

async function openMap(page: Page) {
  await openPipeline(page);
  await page.getByRole("button", { name: "Map: Map" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Open map editor" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Links" }).or(page.getByText("No links yet."))).toBeVisible();
}

async function selectTheLink(page: Page) {
  await page.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("When it occurred")).toBeVisible();
}

async function saveTheTemplate(page: Page) {
  await page.getByRole("button", { name: "Save draft" }).focus();
  await page.keyboard.press("Enter");
}

test("a link of the row template is chosen from the list in Map by keyboard", async ({ page }) => {
  await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  const link = page.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" });
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(link).toHaveAttribute("aria-pressed", "true");
  // The inspector is open on it: its time control is there.
  await expect(page.getByLabel("When it occurred")).toBeVisible();
  registerCovered(REGISTRY, "select-a-map-link-by-keyboard");
});

test("a link is made in Map by keyboard, from its two ends and its type, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: { entities: TWO_ENDPOINTS, edges: [] } });
  await openMap(page);
  const from = page.getByLabel("From entity");
  await from.focus();
  await page.keyboard.type("a");
  const to = page.getByLabel("To entity");
  await to.focus();
  await page.keyboard.type("b");
  await page.getByLabel("Link type").focus();
  await page.keyboard.type("COMM");
  await page.getByRole("button", { name: "Add link" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges).toEqual([
    { type: "COMMUNICATED_WITH", from: "a", to: "b", properties: {} },
  ]);
  registerCovered(REGISTRY, "create-a-map-link-by-keyboard");
});

test("a link's time is bound to a column in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheLink(page);
  await page.getByLabel("When it occurred").focus();
  await page.keyboard.type("From");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges![0]!.temporal).toEqual({ at: { field: "started" } });
  registerCovered(REGISTRY, "bind-a-map-links-time-by-keyboard");
});

test("when a link ended is bound to a column in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, {
    rowTemplate: {
      entities: TWO_ENDPOINTS,
      edges: [{ type: "COMMUNICATED_WITH", from: "a", to: "b", temporal: { at: { field: "started" } }, properties: {} }],
    },
  });
  await openMap(page);
  await selectTheLink(page);
  await page.getByLabel("When it ended").focus();
  await page.keyboard.type("From");
  const column = page.getByLabel("Column holding when it ended");
  await column.focus();
  await page.keyboard.type("en");
  await expect(column).toHaveValue("ended");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges![0]!.temporal).toEqual({
    at: { field: "started" },
    valid_to: { field: "ended", transform: "datetime" },
  });
  registerCovered(REGISTRY, "bind-a-map-links-end-by-keyboard");
});

test("the column holding a link's text is marked in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, {
    rowTemplate: {
      entities: TWO_ENDPOINTS,
      edges: [{ type: "COMMUNICATED_WITH", from: "a", to: "b", temporal: { at: { field: "started" } }, properties: {} }],
    },
  });
  await openMap(page);
  await selectTheLink(page);
  await page.getByLabel("Text the model can read").focus();
  await page.keyboard.type("Message");
  const column = page.getByLabel("Column holding the text");
  await column.focus();
  await page.keyboard.type("text");
  await expect(column).toHaveValue("text");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges![0]!.content).toEqual({ kind: "message_text", field: "text" });
  registerCovered(REGISTRY, "mark-a-map-links-text-by-keyboard");
});

test("a link's classification is bound to the declared column in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(
    page,
    { classification: "OFFICIAL", handling_columns: { classification: "marking" } },
    { rowTemplate: ONE_LINK },
  );
  await openMap(page);
  await selectTheLink(page);
  await page.getByLabel("Override handling for this element").focus();
  await page.keyboard.press(" ");
  const part = page.getByLabel("Classification for this element");
  await part.focus();
  await page.keyboard.type("From");
  await expect(part.locator("option:checked")).toHaveText("From column marking");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges![0]!.handling).toEqual({ classification: { field: "marking" } });
  registerCovered(REGISTRY, "bind-a-map-links-handling-to-a-column-by-keyboard");
});

// --- ADR-127 Amendment 13: the entities of the row template, by keyboard ------------------------------

async function selectTheEntity(page: Page, name: string) {
  await page.getByRole("button", { name }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Entity ref")).toBeVisible();
}

test("an entity of the row template is chosen from the list in Map by keyboard", async ({ page }) => {
  await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  const entity = page.getByRole("button", { name: "Entity 2: b (Endpoint)" });
  await entity.focus();
  await page.keyboard.press("Enter");
  await expect(entity).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Entity ref")).toHaveValue("b");
  registerCovered(REGISTRY, "select-a-map-entity-by-keyboard");
});

test("an entity is renamed in Map by keyboard, and the save carries its links with it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Entity ref").focus();
  await page.keyboard.press("End");
  await page.keyboard.press("Backspace");
  await page.keyboard.type("payer");
  await expect(page.getByRole("button", { name: "Entity 1: payer (Endpoint)" })).toBeVisible();
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const saved = served.templates[0]!.row_template;
  expect((saved.entities as { ref: string }[]).map((e) => e.ref)).toEqual(["payer", "b"]);
  expect(saved.edges![0]).toMatchObject({ from: "payer", to: "b" });
  registerCovered(REGISTRY, "rename-a-map-entity-by-keyboard");
});

test("a binding of an entity is added and changed in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Add a property").focus();
  await page.keyboard.type("value");
  const column = page.getByLabel("Source column");
  await expect(column).toBeVisible();
  await column.focus();
  await page.keyboard.type("en");
  await expect(column).toHaveValue("ended");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const entities = served.templates[0]!.row_template.entities as { properties: Record<string, unknown> }[];
  expect(entities[0]!.properties).toEqual({ value_normalised: { field: "ended" } });
  registerCovered(REGISTRY, "change-a-map-entitys-binding-by-keyboard");
});

test("an entity is deleted in Map by keyboard, and the save drops it and the links it ends", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByRole("button", { name: "Delete element" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Entity 1: a (Endpoint)" })).toHaveCount(0);
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const saved = served.templates[0]!.row_template;
  expect((saved.entities as { ref: string }[]).map((e) => e.ref)).toEqual(["b"]);
  expect(saved.edges).toEqual([]);
  registerCovered(REGISTRY, "delete-a-map-entity-by-keyboard");
});

test("a link is deleted in Map by keyboard, and the save keeps its entities", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheLink(page);
  await page.getByRole("button", { name: "Delete element" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" })).toHaveCount(0);
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const saved = served.templates[0]!.row_template;
  expect(saved.edges).toEqual([]);
  expect(saved.entities).toHaveLength(2);
  registerCovered(REGISTRY, "delete-a-map-link-by-keyboard");
});

// --- the remaining controls on an existing element, by keyboard -----------------------------------------

const WITH_DOCUMENT = {
  entities: [
    ...TWO_ENDPOINTS,
    { ref: "d", pole_class: "object", type: "Document", on_match: "create", properties: {} },
  ],
  edges: ONE_LINK.edges,
};

test("an entity's type and POLE class are changed in Map by keyboard, and the save carries both", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Entity type").focus();
  await page.keyboard.type("Dev");
  await expect(page.getByLabel("Entity type")).toHaveValue("Device");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[0]).toMatchObject({ pole_class: "object", type: "Device" });
  await page.getByLabel("POLE class").focus();
  await page.keyboard.type("person");
  await expect(page.getByLabel("POLE class")).toHaveValue("person");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(2);
  expect(served.templates[1]!.row_template.entities[0]).toMatchObject({ pole_class: "person", type: "Person" });
  registerCovered(REGISTRY, "change-a-map-entitys-pole-class-and-type-by-keyboard");
});

test("an entity's match-on and on-match are set in Map by keyboard, and the save carries both", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Match on").focus();
  await page.keyboard.type("value_normalised");
  const reference = page.getByRole("radio", { name: "reference existing" });
  await reference.focus();
  await page.keyboard.press(" ");
  await expect(reference).toBeChecked();
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[0]).toMatchObject({
    match_on: "value_normalised",
    on_match: "reference",
  });
  registerCovered(REGISTRY, "set-a-map-entitys-match-by-keyboard");
});

test("the content an entity holds is marked in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Content this holds").focus();
  await page.keyboard.type("Image");
  const column = page.getByLabel("Column holding it");
  await column.focus();
  await page.keyboard.type("en");
  await expect(column).toHaveValue("ended");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[0]!.content).toEqual({ kind: "image_file", field: "ended" });
  registerCovered(REGISTRY, "mark-a-map-entitys-content-by-keyboard");
});

test("a Document's own text is marked in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: WITH_DOCUMENT });
  await openMap(page);
  await selectTheEntity(page, "Entity 3: d (Document)");
  await page.getByLabel("Its own text").focus();
  await page.keyboard.type("Document");
  const column = page.getByLabel("Column holding its text");
  await column.focus();
  await page.keyboard.type("text");
  await expect(column).toHaveValue("text");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[2]!.content).toEqual({ kind: "document_text", field: "text" });
  registerCovered(REGISTRY, "mark-a-map-documents-own-text-by-keyboard");
});

test("an entity is made conditional in Map by keyboard, and the save carries its condition", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Conditional element").focus();
  await page.keyboard.press(" ");
  await page.getByLabel("Condition column").focus();
  await page.keyboard.type("en");
  await expect(page.getByLabel("Condition column")).toHaveValue("ended");
  await page.getByLabel("Condition test").focus();
  await page.keyboard.type("eq");
  await expect(page.getByLabel("Condition test")).toHaveValue("equals");
  await page.getByLabel("Condition value").focus();
  await page.keyboard.type("x");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.entities[0]!.when).toEqual({ field: "ended", equals: "x" });
  registerCovered(REGISTRY, "make-a-map-entity-conditional-by-keyboard");
});

test("a link's type is changed in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheLink(page);
  await page.getByLabel("Link type for this link").focus();
  await page.keyboard.type("PAIRED");
  await expect(page.getByLabel("Link type for this link")).toHaveValue("PAIRED_WITH");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  expect(served.templates[0]!.row_template.edges![0]!.type).toBe("PAIRED_WITH");
  registerCovered(REGISTRY, "change-a-map-links-type-by-keyboard");
});

test("a transform is chosen on an existing property binding in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, {
    rowTemplate: {
      entities: [
        { ...TWO_ENDPOINTS[0], properties: { value_normalised: { field: "started" } } },
        TWO_ENDPOINTS[1],
      ],
      edges: ONE_LINK.edges,
    },
  });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Transform", { exact: true }).focus();
  await page.keyboard.type("msisdn");
  await expect(page.getByLabel("Transform", { exact: true })).toHaveValue("msisdn");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const entities = served.templates[0]!.row_template.entities as { properties: Record<string, unknown> }[];
  expect(entities[0]!.properties).toEqual({ value_normalised: { field: "started", transform: "msisdn" } });
  registerCovered(REGISTRY, "choose-a-transform-on-a-map-binding-by-keyboard");
});

test("a literal is set as a property's binding in Map by keyboard, and the save carries it", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Add a property").focus();
  await page.keyboard.type("endpoint_kind");
  await page.getByLabel("Binding kind").focus();
  await page.keyboard.type("Literal");
  await expect(page.getByLabel("Binding kind")).toHaveValue("literal");
  await page.getByLabel("Literal value").focus();
  await page.keyboard.type("phone");
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const entities = served.templates[0]!.row_template.entities as { properties: Record<string, unknown> }[];
  expect(entities[0]!.properties).toEqual({ endpoint_kind: { literal: "phone" } });
  registerCovered(REGISTRY, "set-a-literal-on-a-map-binding-by-keyboard");
});

test("a property's binding is split and marked optional in Map by keyboard, and the save carries both", async ({ page }) => {
  const served = await serve(page, {}, { rowTemplate: ONE_LINK });
  await openMap(page);
  await selectTheEntity(page, "Entity 1: a (Endpoint)");
  await page.getByLabel("Add a property").focus();
  await page.keyboard.type("value");
  await page.getByLabel("Transform", { exact: true }).focus();
  await page.keyboard.type("split");
  await expect(page.getByLabel("Transform", { exact: true })).toHaveValue("split");
  const optional = page.getByLabel("Optional: leave the property out when its cell is empty");
  await optional.focus();
  await page.keyboard.press(" ");
  await expect(optional).toBeChecked();
  await saveTheTemplate(page);
  await expect.poll(() => served.templates.length).toBe(1);
  const entities = served.templates[0]!.row_template.entities as { properties: Record<string, unknown> }[];
  expect(entities[0]!.properties).toEqual({
    value_normalised: { field: "started", transform: "split", optional: true },
  });
  registerCovered(REGISTRY, "split-and-mark-a-map-binding-optional-by-keyboard");
});

test("every registered pipeline-studio action has its own proving test case above", () => {
  assertAllCovered("PIPELINE_STUDIO_ACTIONS", PIPELINE_STUDIO_ACTIONS);
});
