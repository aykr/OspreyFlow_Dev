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
  await page.route("**/*/v1/investigations/*/patterns", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ patterns: [] }) });
  });
  await page.route("**/*/v1/investigations/*/patterns/save", async (route) => {
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
  await page.route("**/*/v1/investigations/*/patterns", async (route) => {
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
  await page.route("**/*/v1/investigations/*/patterns/pattern-1*", async (route) => {
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

test("a condition is added to a node by keyboard, sent by Preview, and removed again", async ({ page }) => {
  // ADR-121 (rule 13). The value field sits on the node; the property it offers is the one indexed,
  // non-sensitive text property the harness's Person declares.
  const previewBodies: { nodes: { where?: Record<string, string> }[] }[] = [];
  await page.route("**/*/v1/investigations/*/patterns/preview", async (route) => {
    previewBodies.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ estimated_count: 2, is_floor: false }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");

  const property = page.getByRole("combobox", { name: "Condition property on a" });
  await expect(property.locator("option")).toHaveText(["family_name"]);

  const value = page.getByRole("textbox", { name: "Condition value on a" });
  await value.focus();
  await page.keyboard.type("Smith");
  await tabToButtonNamed(page, "Add condition");
  await page.keyboard.press("Enter");
  await expect(page.getByText("family_name = Smith")).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "add-condition-to-pattern-node");

  // Typing in the value field is not Delete on the node: the node is still there.
  await value.focus();
  await page.keyboard.press("Backspace");
  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toBeVisible();

  await tabToButtonNamed(page, "Preview");
  await page.keyboard.press("Enter");
  await expect(page.getByText("~2 matches")).toBeVisible();
  expect(previewBodies[0]?.nodes[0]?.where).toEqual({ family_name: "Smith" });

  // The condition's own Remove button comes before the property select and the value field.
  await value.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Remove condition family_name on a" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("family_name = Smith")).toHaveCount(0);
  registerCovered("QUERY_BUILDER_ACTIONS", "remove-condition-from-pattern-node");
});

test("Ask to search: type the question, move to the proposed pattern, preview it, run it", async ({ page }) => {
  // ADR-129 decision 2 (rule 13). The model's proposal is intercepted at the transport; what is
  // proved is the keyboard path: the box takes the question and Enter asks, the proposed pattern is
  // drawn in the builder and reached by Tab, and Preview and Run, the existing routes, are
  // pressed from it. The proposal's own count (4) and the preview's (9) differ, so the case shows
  // the second press asked the preview route and did not reuse the first.
  const asked: { question: string; selected_node_ids: string[] }[] = [];
  await page.route("**/*/v1/investigations/*/patterns/ask", async (route) => {
    asked.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        pattern: {
          nodes: [
            { var: "a", entity_type: "Person", node_id: null },
            { var: "b", entity_type: "Endpoint", node_id: "n-selected" },
          ],
          edges: [{ edge_type: "USES", from_var: "a", to_var: "b" }],
          limit: 1000,
        },
        explanation: "Finds people who use the selected number.",
        estimated_count: 4,
        is_floor: false,
      }),
    });
  });
  await page.route("**/*/v1/investigations/*/patterns/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ estimated_count: 9, is_floor: false }),
    });
  });
  await page.route("**/*/v1/investigations/*/patterns/run", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mode: "sync", subgraph: { nodes: [], edges: [] }, matched_count: 9 }),
    });
  });

  await page.goto("/keyboard/query-builder-harness.html");
  const box = page.getByRole("textbox", { name: "Ask to search" });
  await box.focus();
  await page.keyboard.type("Who uses the selected number?");
  await page.keyboard.press("Enter");

  await expect(page.getByText(/Finds people who use the selected number\./)).toBeVisible();
  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toBeVisible();
  await expect(page.getByRole("group", { name: /Pattern node b: Endpoint · n-selected/ })).toBeVisible();
  await expect(page.getByText("~4 matches")).toBeVisible();
  expect(asked).toEqual([{ question: "Who uses the selected number?", selected_node_ids: ["n-selected"] }]);

  // Move to the proposed pattern: Tab from the question box reaches Ask, then the first node.
  await tabUntil(page, async () =>
    page.evaluate(() => document.activeElement?.getAttribute("aria-label")?.startsWith("Pattern node a") ?? false),
  );
  await tabToButtonNamed(page, "Preview");
  await page.keyboard.press("Enter");
  await expect(page.getByText("~9 matches")).toBeVisible();

  await tabToButtonNamed(page, "Run");
  await page.keyboard.press("Enter");
  await expect(page.getByText("9 node(s) matched.")).toBeVisible();
  registerCovered("QUERY_BUILDER_ACTIONS", "ask-to-search-propose-pattern");
});

test("Ask to search over a pattern already drawn: the replaced pattern is restored by keyboard", async ({ page }) => {
  // ADR-129 decision 2 (rule 13): a proposal replaces what was drawn, so the analyst can press
  // "Restore the previous pattern", reached by Tab, and have it back.
  await page.route("**/*/v1/investigations/*/patterns/ask", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        pattern: {
          nodes: [{ var: "m", entity_type: "Endpoint", node_id: "n-selected" }],
          edges: [],
          limit: 1000,
        },
        explanation: "Finds the selected number.",
        estimated_count: 1,
        is_floor: false,
      }),
    });
  });
  await page.goto("/keyboard/query-builder-harness.html");
  await openPart(page, "Add to the pattern");
  await tabToButtonNamed(page, "Add variable");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toBeVisible();

  const box = page.getByRole("textbox", { name: "Ask to search" });
  await box.focus();
  await page.keyboard.type("Which number is selected?");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: /Pattern node m: Endpoint · n-selected/ })).toBeVisible();
  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toHaveCount(0);

  await box.focus();
  await tabToButtonNamed(page, "Restore the previous pattern");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: /Pattern node a: Person/ })).toBeVisible();
  await expect(page.getByRole("group", { name: /Pattern node m:/ })).toHaveCount(0);
  registerCovered("QUERY_BUILDER_ACTIONS", "restore-the-previous-pattern-after-ask");
});

test("every registered query-builder action has its own proving test case above", () => {
  assertAllCovered("QUERY_BUILDER_ACTIONS", QUERY_BUILDER_ACTIONS);
});
