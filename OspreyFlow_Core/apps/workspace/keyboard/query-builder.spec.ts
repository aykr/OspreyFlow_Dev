// A scripted, keyboard-only walkthrough of the visual query builder — Phase 7 Stage 4, proving
// reachability end to end for the third keyboard-driven surface (`keyboard/query-builder-harness.tsx`'s own
// docstring has the reasoning for a separate harness/spec pair rather than folding into either
// existing one). Like the other two, this file never calls `page.mouse`/`.click()`.
//
// **What each case proves, precisely — real application logic, not a browser default.** Every
// action below mutates `patterns/store.ts`'s own pattern state or crosses a real network call; the
// panel's native `<select>`/`<button>` controls that carry no logic of their own (choosing an
// entity type, the Connect selects) get no case here, the same "a native control needs no proving
// test case" exemption `MetricsPanel`'s own selects already established. `/v1/search`,
// `/v1/patterns/preview` and `/v1/patterns/run` are intercepted so every result is deterministic —
// the same "real network call, mocked at the transport" shape `metrics-panel.spec.ts` uses for
// `/compute/degree`.
import { expect, test, type Page } from "@playwright/test";

import { assertAllCovered, QUERY_BUILDER_ACTIONS, registerCovered } from "./actionRegistry";

const SEARCH_NODE = {
  id: "n42",
  type: "Person",
  properties: { family_name: "Searched" },
  provenance: {
    state: "asserted",
    sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
    first_seen: "2026-01-01T00:00:00Z",
  },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
};

async function tabUntil(page: Page, matches: () => Promise<boolean>, maxTabs = 20): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    if (await matches()) return;
    await page.keyboard.press("Tab");
  }
  if (!(await matches())) throw new Error(`Tab never reached the expected element within ${maxTabs} presses`);
}

async function tabToButtonNamed(page: Page, name: string, maxTabs = 20): Promise<void> {
  await tabUntil(
    page,
    async () => {
      const active = await page.evaluate(() => ({
        tag: document.activeElement?.tagName,
        text: document.activeElement?.textContent ?? "",
      }));
      return active.tag === "BUTTON" && active.text.includes(name);
    },
    maxTabs,
  );
}

/** ADR-096: the Query builder folds into parts; a folded part's controls are hidden, so Tab never
 * reaches them until the part is opened. Opens one by keyboard (Enter on its header) if folded. */
async function openPart(page: Page, name: string): Promise<void> {
  const header = page.getByRole("button", { name, exact: true });
  if ((await header.getAttribute("aria-expanded")) === "true") return;
  await header.focus();
  await page.keyboard.press("Enter");
  await expect(header).toHaveAttribute("aria-expanded", "true");
}

test("Add variable places a new, unpinned pattern node", async ({ page }) => {
  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");

  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "palette-add-variable-node");
  registerCovered("QUERY_BUILDER_ACTIONS", "open-a-folded-part-by-keyboard");
});

test("selecting a search result via the keyboard pins it as a new pattern node", async ({ page }) => {
  // The search box asks `/v1/suggest` as the analyst types (ADR-059), not `/v1/search`; this
  // case still routed the old endpoint and had failed since that change.
  await page.route("**/*/v1/investigations/*/suggest", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ nodes: [SEARCH_NODE], more: false }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  const search = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
  await search.focus();
  await search.fill("search");
  // The search list names a person by name (ADR-074, ADR-076), not by id: this case still waited for
  // "Person: n42" and so timed out once that was done.
  await page.getByRole("option", { name: /Person: Searched/ }).waitFor();
  await page.keyboard.press("Enter");

  await expect(page.getByRole("group", { name: /Pattern node a: Person · n42/ })).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "pin-node-from-search");
});

test("a second, unpinned root is announced live, not only disclosed at Run", async ({ page }) => {
  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter"); // var a — the primary root
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter"); // var b — a second, disconnected, unpinned root

  await expect(page.getByRole("status")).toHaveText(
    "Second root — pin to a known node or connect it to the pattern",
  );
  registerCovered("QUERY_BUILDER_ACTIONS", "second-root-needs-pinning-announced");
});

test("Delete on a focused pattern node removes it", async ({ page }) => {
  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");

  const node = page.getByRole("group", { name: /Pattern node a: Person/ });
  await expect(node).toBeVisible();
  await node.focus();
  await page.keyboard.press("Delete");

  await expect(node).toHaveCount(0);
  registerCovered("QUERY_BUILDER_ACTIONS", "delete-focused-pattern-element");
});

test("Preview reports the principal-filtered estimate before Run is ever pressed", async ({ page }) => {
  await page.route("**/*/v1/investigations/*/patterns/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ estimated_count: 12, is_floor: false }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");
  await tabToButtonNamed(page, "Preview");
  await page.keyboard.press("Enter");

  await expect(page.getByText("~12 matches")).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "run-preview");
});

test("Run executes the pattern and reports the matched count", async ({ page }) => {
  await page.route("**/*/v1/investigations/*/patterns/run", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mode: "sync", subgraph: { nodes: [], edges: [] }, matched_count: 12 }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");
  await tabToButtonNamed(page, "Run");
  await page.keyboard.press("Enter");

  await expect(page.getByText("12 node(s) matched.")).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "submit-run");
});

test("Save writes the pattern and reports its new version, reachable by keyboard alone", async ({
  page,
}) => {
  await page.route("**/*/v1/patterns", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ patterns: [] }) });
  });
  await page.route("**/*/v1/patterns/save", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "row-1",
        pattern_id: "pattern-1",
        version: 1,
        name: "Common contacts",
        owner_id: "analyst-1",
        created_at: "2026-01-01T00:00:00Z",
        definition: { nodes: [], edges: [], limit: 1000 },
      }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");

  await openPart(page, "Save and load");
  const nameField = page.getByRole("textbox", { name: "Pattern name" });
  await nameField.focus();
  await page.keyboard.type("Common contacts");
  await tabToButtonNamed(page, "Save");
  await page.keyboard.press("Enter");

  await expect(page.getByText("Saved as version 1.")).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "save-pattern");
});

test("Load replaces the builder's own pattern with a previously saved one, reachable by keyboard alone", async ({
  page,
}) => {
  await page.route("**/*/v1/patterns", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        patterns: [
          {
            id: "row-1",
            pattern_id: "pattern-1",
            version: 2,
            name: "Common contacts",
            owner_id: "analyst-1",
            created_at: "2026-01-01T00:00:00Z",
            definition: { nodes: [], edges: [], limit: 1000 },
          },
        ],
      }),
    });
  });
  await page.route("**/*/v1/patterns/pattern-1*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "row-1",
        pattern_id: "pattern-1",
        version: 2,
        name: "Common contacts",
        owner_id: "analyst-1",
        created_at: "2026-01-01T00:00:00Z",
        definition: {
          nodes: [{ var: "a", entity_type: "Person", node_id: "n42" }],
          edges: [],
          limit: 1000,
        },
      }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Save and load");
  const savedSelect = page.getByRole("combobox", { name: "Saved patterns" });
  await savedSelect.focus();
  await savedSelect.selectOption("pattern-1");
  await tabToButtonNamed(page, "Load");
  await page.keyboard.press("Enter");

  await expect(page.getByRole("group", { name: /Pattern node a: Person · n42/ })).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "load-saved-pattern");
});

test("every registered query-builder action has its own proving test case above", () => {
  assertAllCovered("QUERY_BUILDER_ACTIONS", QUERY_BUILDER_ACTIONS);
});
