// The Monitoring place's Connection strength tab by keyboard alone (ADR-139 decision 3; CLAUDE.md
// rule 13): a waiting installation-wide version approved by a second holder of the right, withdrawn
// by its own proposer (who is never offered the approval), a new version proposed with an influencer
// written blank by blank, and a case's own override set by its Author. And decision 8: a rule's
// strength blank, in the sentence builder. Never `page.mouse` or `.click()`.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { assertAllCovered, registerCovered, STRENGTH_ACTIONS } from "./actionRegistry";

/** Tabs until `target` is focused — never a counted number of Tabs. */
async function tabUntilFocused(page: Page, target: Locator, max = 80): Promise<void> {
  await expect(target).toBeVisible();
  for (let i = 0; i < max && !(await target.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

const sent = (page: Page) => page.evaluate(() => window.__STRENGTH__!.sent);

test("a second holder of the right approves a waiting version by keyboard", async ({ page }) => {
  await page.goto("/keyboard/strength-harness.html?as=checker");
  const approve = page.getByRole("button", { name: "Approve version 2" });
  await tabUntilFocused(page, approve);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Version 2 is approved and in force.");
  expect((await sent(page)).some((c) => c.method === "POST" && c.path === "/v1/strength-influencers/2/approve")).toBe(true);
  registerCovered("STRENGTH_ACTIONS", "approve-a-waiting-influencer-version-by-keyboard");
});

test("its proposer is never offered the approval, and withdraws it by keyboard", async ({ page }) => {
  await page.goto("/keyboard/strength-harness.html?as=maker");
  await expect(page.getByRole("button", { name: "Approve version 2" })).toBeDisabled();
  await expect(page.getByText("You proposed it, so a second person with the right must approve it.")).toBeVisible();
  const why = page.getByRole("textbox", { name: "Why it goes back (required)" });
  await tabUntilFocused(page, why);
  await page.keyboard.type("The sizes are not yet agreed");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Withdraw it" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Version 2 is sent back.");
  const back = (await sent(page)).find((c) => c.path.endsWith("/send-back"));
  expect(back?.body).toEqual({ words: "The sizes are not yet agreed" });
  expect((await sent(page)).some((c) => c.path.endsWith("/approve"))).toBe(false);
  registerCovered("STRENGTH_ACTIONS", "withdraw-ones-own-influencer-version-by-keyboard");
});

test("a new version is proposed, with an influencer written blank by blank, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/strength-harness.html?as=author");
  await tabUntilFocused(page, page.getByRole("button", { name: "Propose a new version" }));
  await page.keyboard.press("Enter");
  const proposal = page.locator(".strength-panel__proposal");
  await tabUntilFocused(page, proposal.getByRole("textbox", { name: "Label in the legend" }));
  await page.keyboard.type("Find in a shared cell");
  await tabUntilFocused(page, proposal.getByRole("checkbox", { name: "Shared a cell with" }));
  await page.keyboard.press(" ");
  const when = proposal.getByRole("combobox", { name: "When it applies" });
  await tabUntilFocused(page, when);
  await page.keyboard.type("When");
  await expect(when).toHaveValue("record");
  const kind = proposal.getByRole("combobox", { name: "Kind of record" });
  await tabUntilFocused(page, kind);
  await page.keyboard.type("Inc");
  await expect(kind).toHaveValue("Incident");
  const property = proposal.getByRole("combobox", { name: "Its property" });
  await tabUntilFocused(page, property);
  await page.keyboard.type("cat");
  await expect(property).toHaveValue("category");
  await tabUntilFocused(page, proposal.getByRole("checkbox", { name: "find" }));
  await page.keyboard.press(" ");
  const change = proposal.getByRole("combobox", { name: "Change" });
  await tabUntilFocused(page, change);
  await page.keyboard.type("At");
  await expect(change).toHaveValue("floor");
  await tabUntilFocused(page, proposal.getByRole("button", { name: "Add this influencer" }));
  await page.keyboard.press("Enter");
  await expect(proposal).toContainText("Find in a shared cell");
  await tabUntilFocused(page, proposal.getByRole("textbox", { name: "Why, for the approver" }));
  await page.keyboard.type("Finds in a cell are strong evidence");
  await tabUntilFocused(page, page.getByRole("button", { name: "Propose for approval" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Version 3 is proposed; it waits for a second person's approval.");
  const proposed = (await sent(page)).find((c) => c.method === "POST" && c.path === "/v1/strength-influencers");
  const body = proposed?.body as { influencers: { id: string; change: string; trigger: unknown }[]; words: string };
  expect(body.influencers.map((i) => i.id)).toEqual(["direct", "incident-source", "find-in-a-shared-cell"]);
  expect(body.influencers[2]).toMatchObject({
    change: "floor",
    trigger: { entity_type: "Incident", property: "category", values: ["find"] },
  });
  registerCovered("STRENGTH_ACTIONS", "propose-an-influencer-version-by-keyboard");
});

test("the case's Author switches off an influencer in this case by keyboard", async ({ page }) => {
  await page.goto("/keyboard/strength-harness.html?as=author");
  const direct = page.getByRole("group", { name: "Switched off in this case" }).getByRole("checkbox", { name: "Direct link" });
  await tabUntilFocused(page, direct);
  await page.keyboard.press(" ");
  await tabUntilFocused(page, page.getByRole("button", { name: "Save this case's influencers" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("This case's influencers are saved.");
  const put = (await sent(page)).find((c) => c.method === "PUT");
  expect(put?.body).toEqual({ added: [], switched_off: ["direct"], words: "" });
  await expect(page.getByText(/Direct links: none\./)).toBeVisible();
  registerCovered("STRENGTH_ACTIONS", "set-a-case-override-by-keyboard");
});

test("a sentence rule's strength blank is written by keyboard (ADR-139 decision 8)", async ({ page }) => {
  await page.goto("/keyboard/monitoring-harness.html?tab=rules");
  const strength = page.getByRole("combobox", { name: "Strength", exact: true });
  await tabUntilFocused(page, strength, 200);
  await page.keyboard.type("the c");
  await expect(strength).toHaveValue("connection_strength");
  const reaches = page.getByRole("spinbutton", { name: "Reaches" });
  await tabUntilFocused(page, reaches);
  for (let i = 0; i < 6; i++) await page.keyboard.press("Backspace");
  await page.keyboard.type("0.85");
  await expect(reaches).toHaveValue("0.85");
  registerCovered("STRENGTH_ACTIONS", "write-a-strength-rule-by-keyboard");
});

test("every connection-strength keyboard action has a proving case", () => {
  assertAllCovered("STRENGTH_ACTIONS", STRENGTH_ACTIONS);
});
