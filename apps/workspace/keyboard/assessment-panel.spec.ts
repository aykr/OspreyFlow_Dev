// A scripted, keyboard-only walkthrough of the Judgements tab (judgements, gaps, assumptions,
// evidence highlighting) — Phase 8 Stage 4c, `CLAUDE.md` rule 13 applied to the fifth
// keyboard-driven surface (`keyboard/assessment-panel-harness.tsx`'s own docstring has the
// reasoning for a separate harness/spec pair). Like the other four, this file never calls
// `page.mouse`/`.click()`.
//
// Every native `Input`/`Select`'s own Tab-reachability gets no case here — only an action with
// real state mutation, a real network call, or a real canvas-touching effect does, the same
// exemption `watch-panels.spec.ts` already establishes. `/v1/investigations/inv-1/judgements`,
// `.../gaps`, `.../assumptions` and `/v1/yardstick` are intercepted so every result is
// deterministic.
import { expect, test, type Page } from "@playwright/test";

import { ASSESSMENT_PANEL_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __ASSESSMENT_HARNESS__?: { highlightedNodeIds: string[] };
  }
}

async function tabToButtonNamed(page: Page, name: string, maxTabs = 40): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    const active = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      text: document.activeElement?.textContent ?? "",
    }));
    if (active.tag === "BUTTON" && active.text.includes(name)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached a button named "${name}" within ${maxTabs} presses`);
}

async function routeYardstickAndEmptyLists(page: Page): Promise<void> {
  await page.route("**/*/v1/yardstick", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ name: "PHIA", bands: [{ label: "likely", lower: 0.55, upper: 0.75 }] }),
    });
  });
}

test("submitting the judgement form saves it and it appears in the list, reachable by keyboard alone", async ({
  page,
}) => {
  await routeYardstickAndEmptyLists(page);
  let created: Record<string, unknown> | null = null;
  await page.route("**/*/v1/investigations/inv-1/judgements", async (route) => {
    if (route.request().method() === "POST") {
      created = {
        id: "j1",
        investigation_id: "inv-1",
        statement: "The subject is the principal organiser.",
        probability_band: "likely",
        supporting: ["n1"],
        contradicting: [],
        author: "analyst-1",
        created_at: "2026-09-22T00:00:00Z",
        flagged_for_review: false,
        flag_reason: null,
      };
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ judgements: created ? [created] : [] }),
    });
  });
  await page.route("**/*/v1/investigations/inv-1/gaps", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ gaps: [] }) });
  });
  await page.route("**/*/v1/investigations/inv-1/assumptions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ assumptions: [] }) });
  });

  await page.goto("/keyboard/assessment-panel-harness.html");
  await tabToButtonNamed(page, "Add judgement, gap or assumption");
  await page.keyboard.press("Enter");

  const statement = page.getByLabel("Statement");
  await statement.focus();
  await page.keyboard.type("The subject is the principal organiser.");

  const evidencePicker = page.getByRole("combobox", { name: "Add supporting evidence" });
  await evidencePicker.focus();
  await page.keyboard.type("Mercer");
  await page.keyboard.press("Enter");

  await tabToButtonNamed(page, "Save judgement");
  await page.keyboard.press("Enter");

  await expect(page.getByText("The subject is the principal organiser.")).toBeVisible();
  registerCovered("ASSESSMENT_PANEL_ACTIONS", "submit-save-judgement");
});

test("selecting a judgement row highlights its own evidence, reachable by keyboard alone", async ({
  page,
}) => {
  await routeYardstickAndEmptyLists(page);
  const existing = {
    id: "j1",
    investigation_id: "inv-1",
    statement: "The subject is the principal organiser.",
    probability_band: "likely",
    supporting: ["n1"],
    contradicting: [],
    author: "analyst-1",
    created_at: "2026-09-22T00:00:00Z",
    flagged_for_review: false,
    flag_reason: null,
  };
  await page.route("**/*/v1/investigations/inv-1/judgements", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ judgements: [existing] }),
    });
  });
  await page.route("**/*/v1/investigations/inv-1/gaps", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ gaps: [] }) });
  });
  await page.route("**/*/v1/investigations/inv-1/assumptions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ assumptions: [] }) });
  });

  await page.goto("/keyboard/assessment-panel-harness.html");
  await expect(page.getByText("The subject is the principal organiser.")).toBeVisible();

  // The statement is rendered as a real `<button>` inside the row — the same shape
  // `watch-panels.spec.ts`'s own `tabToButtonNamed` already relies on being reachable.
  await tabToButtonNamed(page, "The subject is the principal organiser.");
  await page.keyboard.press("Enter");

  await expect
    .poll(() => page.evaluate(() => window.__ASSESSMENT_HARNESS__?.highlightedNodeIds))
    .toEqual(["n1"]);
  registerCovered("ASSESSMENT_PANEL_ACTIONS", "judgement-row-select-highlights-evidence");
});

test("submitting the gap form saves it and it appears in the list, reachable by keyboard alone", async ({
  page,
}) => {
  await routeYardstickAndEmptyLists(page);
  await page.route("**/*/v1/investigations/inv-1/judgements", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ judgements: [] }) });
  });
  let created: Record<string, unknown> | null = null;
  await page.route("**/*/v1/investigations/inv-1/gaps", async (route) => {
    if (route.request().method() === "POST") {
      created = {
        id: "g1",
        investigation_id: "inv-1",
        question: "Who supplied the vehicle?",
        raised_by: "analyst-1",
        linked_entities: [],
        status: "open",
        created_at: "2026-09-22T00:00:00Z",
      };
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ gaps: created ? [created] : [] }),
    });
  });
  await page.route("**/*/v1/investigations/inv-1/assumptions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ assumptions: [] }) });
  });

  await page.goto("/keyboard/assessment-panel-harness.html");
  await tabToButtonNamed(page, "Add judgement, gap or assumption");
  await page.keyboard.press("Enter");

  const gapTab = page.getByRole("tab", { name: "Gap" });
  await gapTab.focus();
  await page.keyboard.press("Enter");

  const question = page.getByLabel("Question");
  await question.focus();
  await page.keyboard.type("Who supplied the vehicle?");

  await tabToButtonNamed(page, "Save gap");
  await page.keyboard.press("Enter");

  await expect(page.getByText("Who supplied the vehicle?")).toBeVisible();
  registerCovered("ASSESSMENT_PANEL_ACTIONS", "submit-save-gap");
});

test("submitting the assumption form saves it and it appears in the list, reachable by keyboard alone", async ({
  page,
}) => {
  await routeYardstickAndEmptyLists(page);
  await page.route("**/*/v1/investigations/inv-1/judgements", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ judgements: [] }) });
  });
  await page.route("**/*/v1/investigations/inv-1/gaps", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ gaps: [] }) });
  });
  let created: Record<string, unknown> | null = null;
  await page.route("**/*/v1/investigations/inv-1/assumptions", async (route) => {
    if (route.request().method() === "POST") {
      created = {
        id: "a1",
        investigation_id: "inv-1",
        statement: "The subject acted alone.",
        if_false_impact: "The principal-organiser judgement falls over.",
        linked_judgements: [],
        created_at: "2026-09-22T00:00:00Z",
      };
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ assumptions: created ? [created] : [] }),
    });
  });

  await page.goto("/keyboard/assessment-panel-harness.html");
  await tabToButtonNamed(page, "Add judgement, gap or assumption");
  await page.keyboard.press("Enter");

  const assumptionTab = page.getByRole("tab", { name: "Assumption" });
  await assumptionTab.focus();
  await page.keyboard.press("Enter");

  const statement = page.getByLabel("Statement");
  await statement.focus();
  await page.keyboard.type("The subject acted alone.");

  const impact = page.getByLabel("If false, the impact is");
  await impact.focus();
  await page.keyboard.type("The principal-organiser judgement falls over.");

  await tabToButtonNamed(page, "Save assumption");
  await page.keyboard.press("Enter");

  await expect(page.getByText("The subject acted alone.")).toBeVisible();
  registerCovered("ASSESSMENT_PANEL_ACTIONS", "submit-save-assumption");
});

test("every registered assessment-panel action has its own proving test case above", () => {
  assertAllCovered("ASSESSMENT_PANEL_ACTIONS", ASSESSMENT_PANEL_ACTIONS);
});
