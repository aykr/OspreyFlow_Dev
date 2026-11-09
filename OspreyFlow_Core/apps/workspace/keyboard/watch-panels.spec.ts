// A scripted, keyboard-only walkthrough of the watch panels (hotlists, monitors, the alert
// inbox) — Phase 7 Stage 6c Part 2, proving reachability end to end for the fourth keyboard-driven
// surface (`keyboard/watch-panels-harness.tsx`'s own docstring has the reasoning for a separate
// harness/spec pair). Like the other three, this file never calls `page.mouse`/`.click()`.
//
// Every native `Input`/`Select`'s own Tab-reachability gets no case here — only an action with
// real state mutation or a real network call does, the same exemption `query-builder.spec.ts`
// already establishes for its own native controls. `/v1/hotlists`, `/v1/monitors`, `/v1/patterns`,
// and `/v1/alerts` are intercepted so every result is deterministic — the
// same "real network call, mocked at the transport" shape every other keyboard spec in this
// directory already uses.
import { expect, test, type Page } from "@playwright/test";

import { assertAllCovered, registerCovered, WATCH_PANEL_ACTIONS } from "./actionRegistry";

declare global {
  interface Window {
    __WATCH_HARNESS__?: { openedAlertId: string | null };
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

// ADR-133 ruling 3: whom a hotlist's alerts reach — chosen for a new one, from the deployment's
// default, and changed on an existing one by its owner.
test("a new hotlist's audience is chosen, and an existing one's changed, by keyboard alone", async ({ page }) => {
  const sent: { method: string; path: string; body: unknown }[] = [];
  const existing = {
    id: "hl-1", identifier: "+447700900000", identifier_typed: "07700 900000", owner_id: "analyst-1",
    review_date: "2026-12-01", status: "active", created_at: "2026-09-22T00:00:00Z", audience: "only_me",
  };  // prettier-ignore
  await page.route("**/*/v1/investigations/*/hotlists**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") sent.push({ method: request.method(), path, body: request.postDataJSON() });
    if (request.method() === "PUT") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...existing, audience: "team" }) });
      return;
    }
    if (request.method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ...existing, id: "hl-2" }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ hotlists: [existing], audience_default: "team", audience_editable: true }),
    });
  });
  for (const what of ["monitors", "patterns", "alerts"]) {
    await page.route(`**/*/v1/investigations/*/${what}`, async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ [what]: [] }) });
    });
  }

  await page.goto("/keyboard/watch-panels-harness.html");
  const choice = page.getByRole("combobox", { name: "Who its alerts reach" });
  await expect(choice).toHaveValue("team");
  await choice.selectOption("only_me");
  await page.getByRole("textbox", { name: "Identifier" }).fill("07700 900111");
  await page.getByLabel("Review date").fill("2027-01-01");
  await tabToButtonNamed(page, "Add to hotlist");
  await page.keyboard.press("Enter");
  await expect.poll(() => sent.find((s) => s.method === "POST")?.body).toEqual({
    identifier: "07700 900111",
    review_date: "2027-01-01",
    audience: "only_me",
  });
  registerCovered("WATCH_PANEL_ACTIONS", "choose-a-new-hotlists-audience-by-keyboard");

  await page.getByRole("combobox", { name: "Who alerts from 07700 900000 reach" }).selectOption("team");
  await expect(page.getByText("Alerts from 07700 900000 now reach your team too.")).toBeVisible();
  expect(sent.find((s) => s.method === "PUT")).toEqual({
    method: "PUT",
    path: "/v1/investigations/inv-1/hotlists/hl-1/audience",
    body: { audience: "team" },
  });
  registerCovered("WATCH_PANEL_ACTIONS", "change-a-hotlists-audience-by-keyboard");
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

async function serveWatches(page: Page): Promise<{ sent: { method: string; path: string; body: unknown }[] }> {
  const state = { sent: [] as { method: string; path: string; body: unknown }[] };
  const fulfil = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/v1/investigations/inv-1/", "");
    if (request.method() !== "GET") state.sent.push({ method: request.method(), path, body: request.postDataJSON() });
    if (url.pathname === "/v1/investigations")
      return route.fulfill(fulfil([{ id: "inv-1", name: "Case", level: "editor", created_at: "", created_by: "", datasets: ["Prison intel"], dataset_ids: ["ds-1"] }]));
    if (path === "hotlists" && request.method() === "GET")
      return route.fulfill(fulfil({ hotlists: [], audience_default: "only_me", audience_editable: true }));
    if (path === "hotlists") return route.fulfill(fulfil({ id: "h-1" }, 201));
    if (path === "patterns")
      return route.fulfill(fulfil({ patterns: [{ id: "sp1", pattern_id: "pat-1", version: 1, name: "Common contacts", owner_id: "analyst-1", created_at: "2026-10-01T00:00:00Z", definition: { nodes: [], edges: [] } }] }));
    if (path === "monitors" && request.method() === "GET")
      return route.fulfill(fulfil({ monitors: [{ id: "mo-1", pattern_id: "pat-1", owner_id: "analyst-1", status: "active", created_at: "2026-10-01T00:00:00Z", every: "daily", hour: 6 }] }));
    if (path === "monitors") return route.fulfill(fulfil({ id: "mo-2", pattern_id: "pat-1", owner_id: "analyst-1", status: "active", created_at: "2026-10-01T00:00:00Z" }, 201));
    if (path === "monitors/mo-1/schedule")
      return route.fulfill(fulfil({ id: "mo-1", pattern_id: "pat-1", owner_id: "analyst-1", status: "active", created_at: "2026-10-01T00:00:00Z", ...(request.postDataJSON() as object) }));
    if (path === "raised-alerts") return route.fulfill(fulfil({ id: "a-raised" }, 201));
    return route.fulfill(fulfil({}, 404));
  });  // prettier-ignore
  return state;
}

test("a watched pattern's own schedule is set by keyboard (ADR-146 decision 4, G16)", async ({ page }) => {
  const state = await serveWatches(page);
  await page.goto("/keyboard/watch-panels-harness.html");
  const schedule = page.getByRole("combobox", { name: "How often Common contacts runs on its own" });
  await schedule.focus();
  // A native select: its keyboard is the browser's (End chooses the last option).
  await schedule.selectOption("never");
  await expect.poll(() => state.sent.find((s) => s.path === "monitors/mo-1/schedule")?.body).toEqual({ every: "never", hour: 6, weekday: null });
  registerCovered("WATCH_PANEL_ACTIONS", "set-a-watched-patterns-schedule-by-keyboard");
});

test("an entity is watched for, from the Glass, by keyboard (ADR-146 decision 4)", async ({ page }) => {
  const state = await serveWatches(page);
  await page.goto("/keyboard/watch-panels-harness.html");
  await tabToButtonNamed(page, "Watch for this");
  await page.keyboard.press("Enter");
  await expect.poll(() => state.sent.find((s) => s.path === "hotlists")?.body).toMatchObject({ identifier: "+447700900918" });
  await expect(page.getByText(/Watching for \+447700900918/)).toBeVisible();
  registerCovered("WATCH_PANEL_ACTIONS", "watch-for-an-entity-by-keyboard");
});

test("a saved pattern is saved as a watch, from the Glass, by keyboard (ADR-146 decision 4)", async ({ page }) => {
  const state = await serveWatches(page);
  await page.goto("/keyboard/watch-panels-harness.html");
  await tabToButtonNamed(page, "Save as a watch");
  await page.keyboard.press("Enter");
  await expect.poll(() => state.sent.find((s) => s.path === "monitors")?.body).toEqual({ pattern_id: "pat-1" });
  registerCovered("WATCH_PANEL_ACTIONS", "save-a-pattern-as-a-watch-by-keyboard");
});

test("an alert is raised to the dataset, by keyboard (ADR-146 decision 7)", async ({ page }) => {
  const state = await serveWatches(page);
  await page.goto("/keyboard/watch-panels-harness.html");
  await tabToButtonNamed(page, "Raise an alert…");
  await page.keyboard.press("Enter");
  // The title takes focus as the form opens.
  await expect(page.getByRole("textbox", { name: "Title of the alert" })).toBeFocused();
  await page.keyboard.type("Two people at one flat");
  await page.getByRole("textbox", { name: "Why, in words: the reason for the alert" }).focus();
  await page.keyboard.type("Seen together twice");
  await page.getByRole("combobox", { name: "Where the alert goes" }).selectOption("dataset");
  await tabToButtonNamed(page, "Raise the alert");
  await page.keyboard.press("Enter");
  await expect.poll(() => state.sent.find((s) => s.path === "raised-alerts")?.body).toMatchObject({
    title: "Two people at one flat", reason: "Seen together twice", to: "dataset", dataset_id: "ds-1", node_ids: ["n1", "n2"],
  });  // prettier-ignore
  await expect(page.getByRole("status")).toHaveText(/Raised to the dataset/);
  registerCovered("WATCH_PANEL_ACTIONS", "raise-an-alert-by-keyboard");
});

test("every registered watch-panel action has its own proving test case above", () => {
  assertAllCovered("WATCH_PANEL_ACTIONS", WATCH_PANEL_ACTIONS);
});
