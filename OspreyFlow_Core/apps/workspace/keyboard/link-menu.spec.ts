// A scripted, keyboard-only walkthrough of the right-click menu on a link (ADR-080, rule 13). It
// never calls `page.mouse` or `.click()`: `L` selects a focused node's link and `\` opens the same
// menu a right-click opens. The harness's `?fixture=same-as` has three people the engine matched as
// one (s0—s1—s2, links `sa0` and `sa1`, cluster `s0`) and a fourth, `p0`, tied to s2 by an ordinary
// link `ln0`. Writes are intercepted at the transport so the request that went out can be read back.
import { expect, test, type Page } from "@playwright/test";

import { LINK_MENU_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __KEYBOARD__?: {
      selectedEdge: string | null;
      selection: string[];
      linkAction: { edgeId: string; action: string } | null;
    };
    __GROUPED__?: number;
    __CANVAS__?: { reproject: (clusterIds: Record<string, string>) => void };
  }
}

const REGISTRY = "LINK_MENU_ACTIONS";
const FIXTURE = "/keyboard/harness.html?fixture=same-as";
const menu = (page: Page) => page.locator(".radial-menu__list[role='menu']");
const selectedEdge = (page: Page) => page.evaluate(() => window.__KEYBOARD__?.selectedEdge);
const grouped = (page: Page) => page.evaluate(() => window.__GROUPED__);

/** Tab along the open menu until the entry called `name` has focus. */
async function tabToEntry(page: Page, name: string | RegExp) {
  const entry = page.getByRole("menuitem", { name });
  for (let presses = 0; presses < 10; presses++) {
    if (await entry.evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  await expect(entry).toBeFocused();
}

/** Focus the canvas (s0), then select the link `L` reaches and open its menu with `\`. */
async function openMenuOnFirstLink(page: Page, walk: string[] = []) {
  await page.goto(FIXTURE);
  await page.getByRole("application", { name: "Network canvas" }).focus();
  for (const key of walk) await page.keyboard.press(key);
  await page.keyboard.press("l");
}

async function openSameAsMenu(page: Page) {
  await openMenuOnFirstLink(page);
  await expect.poll(() => selectedEdge(page)).toBe("sa0");
  await page.keyboard.press("\\");
  await expect(menu(page)).toBeVisible();
}

/** s0 → s1 → back along ArrowLeft to s2, whose first link by id is the ordinary one, `ln0`. */
async function openOrdinaryMenu(page: Page) {
  await openMenuOnFirstLink(page, ["ArrowRight", "ArrowLeft"]);
  await expect.poll(() => selectedEdge(page)).toBe("ln0");
  await page.keyboard.press("\\");
  await expect(menu(page)).toBeVisible();
}

test("\\ on a selected same-as link opens its menu, with the entries a same-as link has", async ({ page }) => {
  await openSameAsMenu(page);
  const labels = await page.getByRole("menuitem").allTextContents();
  expect(labels.map((l) => l.trim())).toEqual([
    "Collapse into one node",
    "Confirm as the same",
    "Mark as not the same",
    "Explain this link",
    "Add a note",
    "Hide link",
  ]);
  // The first entry has focus on opening, as in the node menu.
  await expect(page.getByRole("menuitem", { name: "Collapse into one node" })).toBeFocused();
  registerCovered(REGISTRY, "backslash-opens-the-menu-of-a-selected-same-as-link");
});

test("Collapse into one node folds the matched people into one, and the Group Node's menu opens them again", async ({
  page,
}) => {
  await openSameAsMenu(page);
  expect(await grouped(page)).toBe(0);
  await page.keyboard.press("Enter"); // Collapse into one node
  await expect(menu(page)).toBeHidden();
  // The whole cluster (s0, s1, s2) is one node now; nothing was written anywhere.
  await expect.poll(() => grouped(page)).toBe(3);
  registerCovered(REGISTRY, "collapse-folds-the-matched-nodes-into-one");

  // The Group Node is the way back: its own menu has "Expand group". Focus is back on the canvas
  // and on the Group Node, so `\` opens that node's menu.
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeFocused();
  await page.keyboard.press("\\");
  await expect(menu(page)).toBeVisible();
  await tabToEntry(page, "Expand group");
  await page.keyboard.press("Enter");
  await expect.poll(() => grouped(page)).toBe(0);
  registerCovered(REGISTRY, "group-node-menu-expands-the-group");
});

test("Moving the resolution slider opens a same-as fold, since the cluster it was made from has changed", async ({
  page,
}) => {
  await openSameAsMenu(page);
  await page.keyboard.press("Enter"); // Collapse into one node
  await expect.poll(() => grouped(page)).toBe(3);
  // The slider moves: the server sends a `reproject` delta and the cluster splits into three.
  await page.evaluate(() => window.__CANVAS__!.reproject({ s0: "s0", s1: "s1", s2: "s2" }));
  await expect.poll(() => grouped(page)).toBe(0);
  // The analyst is told why the nodes are back.
  await expect(page.getByText(/resolution changed/i)).toBeVisible();
  registerCovered(REGISTRY, "moving-the-resolution-slider-opens-a-same-as-fold");
});

test("Confirm as the same asks why first, and sends the reason with the two ends", async ({ page }) => {
  await openSameAsMenu(page);
  let body: unknown = null;
  await page.route("**/*/resolution/link", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ seq: 2, op: "reproject", merged: 1, split: 0, affected: 2 }),
    });
  });
  await tabToEntry(page, "Confirm as the same");
  await page.keyboard.press("Enter");

  // Nothing is sent until the box has a reason. The box takes focus, so typing goes straight in.
  const box = page.getByRole("textbox", { name: /Why\?/ });
  await expect(box).toBeFocused();
  expect(body).toBeNull();
  await page.keyboard.type("Same date of birth and address in two sources.");
  await page.keyboard.press("Control+Enter");

  await expect.poll(() => body).toEqual({
    node_a: "s0",
    node_b: "s1",
    reason: "Same date of birth and address in two sources.",
  });
  await expect(box).toHaveCount(0);
  registerCovered(REGISTRY, "confirm-asks-why-and-sends-the-reason");
});

test("Mark as not the same asks why first, and sends the reason with the two ends", async ({ page }) => {
  await openSameAsMenu(page);
  let body: unknown = null;
  await page.route("**/*/resolution/split", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ seq: 2, op: "reproject", merged: 0, split: 1, affected: 2 }),
    });
  });
  await tabToEntry(page, "Mark as not the same");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox", { name: /Why\?/ })).toBeFocused();
  await page.keyboard.type("Different people: the dates of birth are twenty years apart.");
  // The confirming button by keyboard, not only the shortcut.
  await page.keyboard.press("Tab"); // Cancel
  await page.keyboard.press("Tab"); // Mark as not the same
  await expect(page.getByRole("button", { name: "Mark as not the same" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => body).toEqual({
    node_a: "s0",
    node_b: "s1",
    reason: "Different people: the dates of birth are twenty years apart.",
  });
  registerCovered(REGISTRY, "mark-not-same-asks-why-and-sends-the-reason");
});

test("Without a reason the confirm button stays off and Ctrl+Enter sends nothing", async ({ page }) => {
  await openSameAsMenu(page);
  let sent = false;
  await page.route("**/*/resolution/link", async (route) => {
    sent = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await tabToEntry(page, "Confirm as the same");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox", { name: /Why\?/ })).toBeFocused();
  await expect(page.getByRole("button", { name: "Confirm", exact: true })).toBeDisabled();
  await page.keyboard.press("Control+Enter");
  await page.keyboard.type("   "); // spaces are not a reason
  await page.keyboard.press("Control+Enter");
  await page.waitForTimeout(300);
  expect(sent).toBe(false);
  await expect(page.getByRole("textbox", { name: /Why\?/ })).toBeVisible();
  registerCovered(REGISTRY, "reason-is-required-before-confirming");
});

test("Escape closes the reason box and sends nothing", async ({ page }) => {
  await openSameAsMenu(page);
  let sent = false;
  await page.route("**/*/resolution/*", async (route) => {
    sent = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await tabToEntry(page, "Confirm as the same");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Typed, then thought better of it.");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("textbox", { name: /Why\?/ })).toHaveCount(0);
  await page.waitForTimeout(300);
  expect(sent).toBe(false);
  registerCovered(REGISTRY, "escape-cancels-the-reason-box-and-sends-nothing");
});

test("Explain this link shows how the cluster the two are in scored", async ({ page }) => {
  await openSameAsMenu(page);
  let url: string | null = null;
  await page.route("**/*/resolution/explain/*", async (route) => {
    url = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        cluster_id: "s0",
        member_node_ids: ["s0", "s1", "s2"],
        pairs: [
          {
            node_a: "s0",
            node_b: "s1",
            edge_type: "SAME_AS",
            score: 0.93,
            model_version: "splink-3.9.9-config-1",
            comparison_vector: null,
            manually_asserted: false,
            meets_threshold: true,
          },
        ],
      }),
    });
  });
  await tabToEntry(page, "Explain this link");
  await page.keyboard.press("Enter");
  await expect.poll(() => url).toContain("/resolution/explain/s0");
  await expect(page.getByText("Cluster explanation")).toBeVisible();
  registerCovered(REGISTRY, "explain-this-link-shows-the-cluster");
});

test("Hide link from the menu hides it, and Show hidden links brings it back", async ({ page }) => {
  await openSameAsMenu(page);
  await tabToEntry(page, "Hide link");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Show hidden links (1)" })).toBeVisible();
  await expect.poll(() => selectedEdge(page)).toBeNull();
  registerCovered(REGISTRY, "hide-link-from-the-menu");
});

test("Add a note selects the link and tells the Inspector to take the analyst to the notes", async ({ page }) => {
  await openSameAsMenu(page);
  await tabToEntry(page, "Add a note");
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.linkAction))
    .toEqual({ edgeId: "sa0", action: "note" });
  await expect.poll(() => selectedEdge(page)).toBe("sa0");
  registerCovered(REGISTRY, "add-a-note-hands-over-to-the-inspector");
});

test("A link of another type offers Change and the history, and each hands over to the Inspector", async ({
  page,
}) => {
  await openOrdinaryMenu(page);
  const labels = await page.getByRole("menuitem").allTextContents();
  expect(labels.map((l) => l.trim())).toEqual([
    "Show events (1)",
    "Change link…",
    "Show change history",
    "Add a note",
    "Hide link",
  ]);
  await page.keyboard.press("Enter"); // Show events (1), the first entry (ADR-089)
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.linkAction))
    .toEqual({ edgeId: "ln0", action: "events" });
  registerCovered(REGISTRY, "show-events-hands-over-to-the-inspector");

  await openOrdinaryMenu(page);
  await tabToEntry(page, "Change link…");
  await page.keyboard.press("Enter"); // Change link…
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.linkAction))
    .toEqual({ edgeId: "ln0", action: "change" });

  // The same menu again, from a fresh page, for the history entry.
  await openOrdinaryMenu(page);
  await tabToEntry(page, "Show change history");
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.linkAction))
    .toEqual({ edgeId: "ln0", action: "history" });
  registerCovered(REGISTRY, "other-links-offer-change-and-history-and-hand-over");
});

test("every registered link-menu action has its own proving test case above", () => {
  assertAllCovered("LINK_MENU_ACTIONS", LINK_MENU_ACTIONS);
});
