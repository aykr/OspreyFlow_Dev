// A keyboard-only walkthrough of the administrator's *Proposed types* list (ADR-090 C3, rule 13):
// opened from its top-bar button, each proposal promoted (with the basis chosen, and renamed when
// the server says its name is taken), rejected or retired, each with a reason. It never calls
// `page.mouse` or `.click()`. The routes are answered at the transport by a small stateful stand-in
// that refuses as the server does: a decision with no reason, and a promotion under a taken name.
import { expect, test, type Page } from "@playwright/test";

import { PROPOSED_TYPES_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PROPOSED_TYPES_ACTIONS";

function proposal(id: string, name: string, label: string, status = "pending") {
  return {
    id, name, label, status,
    from_types: ["Person"], to_types: ["Person"], directed: false,
    investigation_id: "inv-1", owning_unit: "unit-1", proposed_by: "analyst-1",
    proposed_at: "2026-10-05T10:00:00Z", reason: `Why ${label}`,
    promoted_name: status === "promoted" ? name : null,
  };
}

async function serve(page: Page, opts: { taken?: string } = {}) {
  const rows = [proposal("p1", "KNOWN_TO", "Known to"), proposal("p2", "SEEN_WITH", "Seen with", "promoted")];
  const decisions: { url: string; body: Record<string, unknown> }[] = [];
  await page.route("**/*/v1/admin/link-types**", async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ proposals: rows }) });
      return;
    }
    const body = request.postDataJSON() as Record<string, unknown>;
    decisions.push({ url: request.url(), body });
    if (!String(body.reason ?? "").trim()) {
      await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ error: "proposal_refused", detail: "Say why." }) });
      return;
    }
    const [, id, verb] = /link-types\/([^/]+)\/?(\w+)?$/.exec(request.url()) ?? [];
    if (id === "retire") {
      const row = rows.find((r) => r.promoted_name === body.name)!;
      row.status = "retired";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ proposals: [row] }) });
      return;
    }
    const row = rows.find((r) => r.id === id)!;
    if (verb === "promote" && opts.taken === row.name && !body.rename_to) {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ error: "proposal_refused", detail: `Its links do not all fit ${row.name} as promoted: promote it under a new name.` }),
      });
      return;
    }
    row.status = verb === "promote" ? "promoted" : "rejected";
    row.promoted_name = verb === "promote" ? String(body.rename_to ?? row.name) : null;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row) });
  });
  return decisions;
}

async function openByKeyboard(page: Page) {
  await page.goto("/keyboard/proposed-types-harness.html");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Proposed types" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Proposed types" })).toBeFocused();
  await expect(page.getByText("Known to", { exact: true })).toBeVisible();
}

/** Tabs until the focused element's accessible name is `name`. */
async function tabTo(page: Page, name: string, max = 20) {
  for (let i = 0; i < max; i++) {
    const label = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el?.getAttribute("aria-label") ?? el?.closest("label")?.textContent ?? el?.textContent ?? "";
    });
    if (label.trim() === name || label.trim().startsWith(name)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached "${name}"`);
}

test("the list opens from its top-bar button and Escape closes it", async ({ page }) => {
  await serve(page);
  await openByKeyboard(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Proposed types" })).toHaveCount(0);
  registerCovered(REGISTRY, "open-the-list-from-the-top-bar-and-escape-closes-it");
});

test("promote by keyboard: the basis is asked, then sent with the reason", async ({ page }) => {
  const decisions = await serve(page);
  await openByKeyboard(page);
  await tabTo(page, "Promote Known to…");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Why? (required)")).toBeFocused();
  await page.keyboard.type("A loader backs it.");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("alert")).toHaveText(/Direct or Probabilistic/);
  expect(decisions).toHaveLength(0);
  await page.getByLabel(/^Direct/).focus();
  await page.keyboard.press("Space");
  await expect(page.getByLabel(/^Direct/)).toBeChecked();
  await page.getByLabel("Why? (required)").focus();
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/Known to promoted/);
  expect(decisions[0]!.body).toEqual({ basis: "direct", reason: "A loader backs it." });
  registerCovered(REGISTRY, "promote-by-keyboard-choosing-the-basis");
});

test("a name taken by a type its links do not fit is promoted under a new ID, by keyboard", async ({ page }) => {
  const decisions = await serve(page, { taken: "KNOWN_TO" });
  await openByKeyboard(page);
  await tabTo(page, "Promote Known to…");
  await page.keyboard.press("Enter");
  await page.getByLabel(/^Probabilistic/).focus();
  await page.keyboard.press("Space");
  await page.getByLabel("Why? (required)").focus();
  await page.keyboard.type("Its own type.");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("alert")).toHaveText(/under a new name/);
  await expect(page.getByLabel("Promote as (a new type ID)")).toBeFocused();
  await page.keyboard.type("knows_staff_at");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/promoted/);
  expect(decisions.at(-1)!.body).toEqual({ basis: "probabilistic", reason: "Its own type.", rename_to: "KNOWS_STAFF_AT" });
  registerCovered(REGISTRY, "rename-at-promotion-by-keyboard");
});

test("reject by keyboard, with a reason", async ({ page }) => {
  const decisions = await serve(page);
  await openByKeyboard(page);
  await tabTo(page, "Reject Known to…");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Use Associate of.");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/Known to rejected/);
  expect(decisions[0]!.url).toMatch(/link-types\/p1\/reject$/);
  registerCovered(REGISTRY, "reject-by-keyboard");
});

test("retire a promoted type by keyboard, with a reason", async ({ page }) => {
  const decisions = await serve(page);
  await openByKeyboard(page);
  await tabTo(page, "Retire Seen with…");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Superseded.");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/Seen with retired/);
  expect(decisions[0]!.body).toEqual({ name: "SEEN_WITH", reason: "Superseded." });
  expect(await page.evaluate(() => window.__DECIDED__)).toBe(1);
  registerCovered(REGISTRY, "retire-by-keyboard");
});

test("every registered proposed-types action has its own proving test case above", () => {
  assertAllCovered("PROPOSED_TYPES_ACTIONS", PROPOSED_TYPES_ACTIONS);
});
