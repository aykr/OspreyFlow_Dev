// A scripted, keyboard-only walkthrough of the watch panels (hotlists, monitors, the alert
// inbox) — Phase 7 Stage 6c Part 2, proving reachability end to end for the fourth keyboard-driven
// surface (`keyboard/watch-panels-harness.tsx`'s own docstring has the reasoning for a separate
// harness/spec pair). Like the other three, this file never calls `page.mouse`/`.click()`.
//
// Every native `Input`/`Select`'s own Tab-reachability gets no case here — only an action with
// real state mutation or a real network call does, the same exemption `query-builder.spec.ts`
// already establishes for its own native controls. `/v1/hotlists`, `/v1/monitors`, `/v1/patterns`,
// `/v1/alerts` and `/v1/alerts/{id}/jump` are intercepted so every result is deterministic — the
// same "real network call, mocked at the transport" shape every other keyboard spec in this
// directory already uses.
import { expect, test, type Page } from "@playwright/test";

import { assertAllCovered, registerCovered, WATCH_PANEL_ACTIONS } from "./actionRegistry";

declare global {
  interface Window {
    __WATCH_HARNESS__?: { openedInvestigationId: string | null };
  }
}

async function tabUntil(page: Page, matches: () => Promise<boolean>, maxTabs = 30): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    if (await matches()) return;
    await page.keyboard.press("Tab");
  }
  if (!(await matches())) throw new Error(`Tab never reached the expected element within ${maxTabs} presses`);
}

async function tabToButtonNamed(page: Page, name: string, maxTabs = 30): Promise<void> {
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

test("submitting the hotlist form creates a hotlist and it appears in the list, reachable by keyboard alone", async ({
  page,
}) => {
  let created = false;
  await page.route("**/*/v1/investigations/*/hotlists", async (route) => {
    if (route.request().method() === "POST") {
      created = true;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "hl-1",
          identifier: "+447700900000",
          owner_id: "analyst-1",
          review_date: "2026-12-01",
          status: "active",
          created_at: "2026-09-22T00:00:00Z",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        hotlists: created
          ? [
              {
                id: "hl-1",
                identifier: "+447700900000",
                owner_id: "analyst-1",
                review_date: "2026-12-01",
                status: "active",
                created_at: "2026-09-22T00:00:00Z",
              },
            ]
          : [],
      }),
    });
  });
  await page.route("**/*/v1/investigations/*/monitors", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ monitors: [] }) });
  });
  await page.route("**/*/v1/investigations/*/patterns", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ patterns: [] }) });
  });
  await page.route("**/*/v1/investigations/*/alerts", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ alerts: [] }) });
  });

  await page.goto("/keyboard/watch-panels-harness.html");
  const identifier = page.getByRole("textbox", { name: "Identifier" });
  await identifier.focus();
  await page.keyboard.type("+447700900000");
  // `.fill()`, not `page.keyboard.type` — a native `<input type="date">`'s segmented keyboard
  // interaction (month/day/year) makes typing a literal date string unreliable across browsers;
  // `.fill()` sets the value directly in the `YYYY-MM-DD` shape the element expects, the same
  // "real interaction, not a mouse click" allowance `query-builder.spec.ts`'s own `search.fill(...)`
  // already establishes for a combobox in this directory.
  const reviewDate = page.getByLabel("Review date");
  await reviewDate.fill("2026-12-01");
  await tabToButtonNamed(page, "Add to hotlist");
  await page.keyboard.press("Enter");

  await expect(page.getByText("+447700900000")).toBeVisible();
  registerCovered("WATCH_PANEL_ACTIONS", "submit-create-hotlist");
});

test("submitting the monitor form turns a saved pattern into a monitor, reachable by keyboard alone", async ({
  page,
}) => {
  await page.route("**/*/v1/investigations/*/hotlists", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ hotlists: [] }) });
  });
  await page.route("**/*/v1/investigations/*/patterns", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        patterns: [
          {
            id: "row-1",
            pattern_id: "pattern-1",
            version: 1,
            name: "Common contacts",
            owner_id: "analyst-1",
            created_at: "2026-01-01T00:00:00Z",
            definition: { nodes: [], edges: [], limit: 1000 },
          },
        ],
      }),
    });
  });
  let created = false;
  await page.route("**/*/v1/investigations/*/monitors", async (route) => {
    if (route.request().method() === "POST") {
      created = true;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "mon-1",
          pattern_id: "pattern-1",
          owner_id: "analyst-1",
          status: "active",
          created_at: "2026-09-22T00:00:00Z",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        monitors: created
          ? [
              {
                id: "mon-1",
                pattern_id: "pattern-1",
                owner_id: "analyst-1",
                status: "active",
                created_at: "2026-09-22T00:00:00Z",
              },
            ]
          : [],
      }),
    });
  });
  await page.route("**/*/v1/investigations/*/alerts", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ alerts: [] }) });
  });

  await page.goto("/keyboard/watch-panels-harness.html");
  const patternSelect = page.getByRole("combobox", { name: "Saved pattern" });
  await patternSelect.focus();
  await patternSelect.selectOption("pattern-1");
  await tabToButtonNamed(page, "Turn into monitor");
  await page.keyboard.press("Enter");

  // `page.getByText` alone is ambiguous here: the saved-pattern `<select>`'s own `<option>` and
  // the monitor list row both carry the text "Common contacts" — scoped to `<li>` to match only
  // the real, visible list row this action is actually proving.
  await expect(page.locator("li").filter({ hasText: "Common contacts" })).toBeVisible();
  registerCovered("WATCH_PANEL_ACTIONS", "submit-create-monitor");
});

test("jumping from an alert calls the real jump route and shows the result, reachable by keyboard alone", async ({
  page,
}) => {
  await page.route("**/*/v1/investigations/*/hotlists", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ hotlists: [] }) });
  });
  await page.route("**/*/v1/investigations/*/monitors", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ monitors: [] }) });
  });
  await page.route("**/*/v1/investigations/*/patterns", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ patterns: [] }) });
  });
  await page.route("**/*/v1/investigations/*/alerts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        alerts: [
          {
            id: "alert-1",
            rule_id: "hotlist:hl-1",
            owner_id: "analyst-1",
            mode: "full",
            referent_node_ids: ["n1"],
            evidence_available: true,
            investigation_id: "inv-source-1",
            created_at: "2026-09-22T00:00:00Z",
            hotlist: { identifier: "07700 900640", kept_as_written: false, review_date: "2027-01-31" },
            fired_on: [
              {
                type: "Endpoint",
                label: "+447700900640",
                files: [{ name: "pid_seized_comms_batch2.csv", row: 3 }],
                more_files: 0,
              },
            ],
          },
        ],
      }),
    });
  });
  await page.route("**/*/v1/investigations/*/alerts/alert-1/jump", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        investigation: {
          id: "inv-branch-1",
          created_at: "2026-09-22T00:00:00Z",
          created_by: "analyst-1",
          owning_unit: "unit-1",
          branched_from: "inv-source-1",
        },
        seeded_count: 1,
      }),
    });
  });

  await page.goto("/keyboard/watch-panels-harness.html");
  await expect(page.getByText("Hotlist: 07700 900640 · review by 31 Jan 2027")).toBeVisible();
  await tabToButtonNamed(page, "Jump into investigation");
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("jump-seeded-summary")).toBeVisible();
  registerCovered("WATCH_PANEL_ACTIONS", "alert-row-jump");

  await tabToButtonNamed(page, "Open investigation");
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__WATCH_HARNESS__?.openedInvestigationId))
    .toBe("inv-branch-1");
  registerCovered("WATCH_PANEL_ACTIONS", "jump-result-open-investigation");
});

test("every registered watch-panel action has its own proving test case above", () => {
  assertAllCovered("WATCH_PANEL_ACTIONS", WATCH_PANEL_ACTIONS);
});
