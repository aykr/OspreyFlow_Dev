// *Needs you* by keyboard alone (ADR-145 decision 11, A2; L2.7; `CLAUDE.md` rule 13): the top bar's
// control opened, each entry's tip read with it as it takes focus, an overdue promotion opening Admin's
// Operations and a dataset's proposals its Model tab, Escape giving focus back; and in the Studio, the
// reminder above the other tabs opening *1 Model · n proposed*. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { NEEDS_YOU_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "NEEDS_YOU_ACTIONS";
const HARNESS = "/keyboard/needs-you-harness.html";

async function openPanel(page: Page) {
  const button = page.getByRole("button", { name: /^Needs you · 3/ });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Needs you" })).toBeVisible();
}

function opened(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __opened: string[] }).__opened);
}

test("Needs you opens, each entry's tip is read with it, and Escape gives focus back", async ({ page }) => {
  await page.goto(HARNESS);
  await openPanel(page);
  await page.keyboard.press("Tab");
  const first = page.getByRole("button", { name: /Promotion SYN-load-7/ });
  await expect(first).toBeFocused();
  await expect(first).toHaveAccessibleDescription(/waited past the days your administrator set/);
  await page.keyboard.press("Tab");
  const proposals = page.getByRole("button", { name: /2 proposed link types to decide in Harbour/ });
  await expect(proposals).toBeFocused();
  await expect(proposals).toHaveAccessibleDescription(/add each to the draft model or decline it/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Needs you" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Needs you · 3/ })).toBeFocused();
  registerCovered(REGISTRY, "read-a-needs-you-entrys-tip-by-keyboard");
});

test("the reader's scheduled loads' notices are reached by Tab, each read with its tip, and how many more is said (ADR-110 Amendment 19)", async ({ page }) => {
  await page.goto(`${HARNESS}?notices=1`);
  const button = page.getByRole("button", { name: /^Needs you · 26/ });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Needs you" })).toBeVisible();
  await page.keyboard.press("Tab"); // the overdue promotion
  await page.keyboard.press("Tab");
  const refused = page.getByText(/due 10 November 2026 at 06:00 was refused: it no longer reaches/);
  await expect(refused).toBeFocused();
  await expect(refused).toHaveAccessibleDescription(/Its pipeline's Runs, in the Ingest Studio, say what happened/);
  await page.keyboard.press("Tab");
  await expect(page.getByText(/due 9 November 2026 at 06:00 failed\. Its pipeline's Runs/)).toBeFocused();
  await page.keyboard.press("Tab");
  const more = page.getByText(/21 more notices of your scheduled loads, not listed here/);
  await expect(more).toBeFocused();
  await expect(more).toHaveAccessibleDescription(/list every run of its schedule/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Needs you" })).toHaveCount(0);
  await expect(button).toBeFocused();
});

test("an overdue promotion opens Operations, and a dataset's proposals its Model tab, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await openPanel(page);
  await page.getByRole("button", { name: /Promotion SYN-load-7/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Needs you" })).toHaveCount(0);
  expect(await opened(page)).toEqual(["operations"]);
  registerCovered(REGISTRY, "open-operations-from-needs-you-by-keyboard");
  await openPanel(page);
  await page.getByRole("button", { name: /2 proposed link types to decide in Harbour/ }).focus();
  await page.keyboard.press("Enter");
  expect(await opened(page)).toEqual(["operations", "model:SYN-ds-a"]);
  registerCovered(REGISTRY, "open-a-datasets-model-tab-from-needs-you-by-keyboard");
});

test("the Studio's reminder opens 1 Model · n proposed by keyboard, its tip read with it", async ({ page }) => {
  await page.goto("/keyboard/ingest-studio-harness.html?proposed=1");
  const reminder = page.getByRole("button", { name: "2 proposed link types wait for you on the Model tab." });
  await reminder.focus();
  await expect(reminder).toHaveAccessibleDescription(/Decide them on 1 Model/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "1 Model · 2 proposed" })).toHaveAttribute("aria-selected", "true");
  await expect(reminder).toHaveCount(0);
  registerCovered(REGISTRY, "open-the-model-tab-from-the-studios-reminder-by-keyboard");
});

// The real path from Needs you into the Studio (`admin/needsYou/openings.ts`): the request App leaves
// in the session before the case opens is taken by the Studio drawn on that dataset, which opens on
// 1 Model; one for another dataset is left waiting.
test("a Needs you request opens the Studio on its dataset's Model tab, and not on another's", async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("osprey.needsYou.opening", JSON.stringify([{ kind: "studio", tab: "model", datasetId: "harbour-extract" }])),
  );
  await page.goto("/keyboard/ingest-studio-harness.html?proposed=1");
  await expect(page.getByRole("tab", { name: "1 Model · 2 proposed" })).toHaveAttribute("aria-selected", "true");
  expect(await page.evaluate(() => sessionStorage.getItem("osprey.needsYou.opening"))).toBeNull();
  const other = await page.context().newPage();
  await other.addInitScript(() =>
    sessionStorage.setItem("osprey.needsYou.opening", JSON.stringify([{ kind: "studio", tab: "model", datasetId: "carrier-records" }])),
  );
  await other.goto("/keyboard/ingest-studio-harness.html?proposed=1");
  await expect(other.getByRole("tab", { name: "3 Pipelines" })).toHaveAttribute("aria-selected", "true");
  expect(await other.evaluate(() => sessionStorage.getItem("osprey.needsYou.opening"))).toContain("carrier-records");
});

// ADR-145 Amendment 4 decision 12 (L2.7): Home's Your access and tasks (Amendment 11), by keyboard:
// each line's why read with it, a case, a Model tab and Operations opened, and Why can I do this? opened.
test("what you answer for opens where to act, its why read with each line, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/answers-harness.html");
  const author = page.getByRole("button", { name: "Author of Harbour wing review" });
  await author.focus();
  await expect(author).toHaveAccessibleDescription(/^Why: Answers for the case/);
  await page.keyboard.press("Enter");
  const model = page.getByRole("button", { name: /2 proposed link types to decide/ });
  await model.focus();
  await expect(model).toHaveAccessibleDescription("Why: Given by your Data Engineer role.");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: /^Reviewer of promotions/ }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => (window as unknown as { __opened: string[] }).__opened)).toEqual([
    "case:SYN-c1", "model:SYN-ds-a", "operations",
  ]); // prettier-ignore
  registerCovered(REGISTRY, "open-what-you-answer-for-by-keyboard");
  const byPlace = page.getByText("What you can do, by place");
  await byPlace.focus();
  await page.keyboard.press("Enter");
  const why = page.getByText(/^Review promotions:/);
  await why.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Given by your Data Engineer role.").first()).toBeVisible();
  registerCovered(REGISTRY, "read-why-i-can-do-this-by-keyboard");
});

// ADR-145 Amendment 11 (the owner's ruling, 13 November 2026): on Home, *Your access and tasks* spans the
// full width below the two columns, never inside the left one, and its sub-headings are set beneath its own
// title. Measured in a browser, at 1440 wide, in the dark, light and GOV.UK looks.
for (const look of ["dark", "light", "govuk"] as const) {
  test(`Home's access and tasks spans both columns below them, its sub-headings beneath its title (${look})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1200 });
    await page.goto(`/keyboard/answers-harness.html?home=1${look === "govuk" ? "&brand=govuk" : ""}`);
    if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    const section = page.locator("section[aria-labelledby='answers-for']");
    await expect(section.getByRole("heading", { level: 2, name: "Your access and tasks" })).toBeVisible();
    await expect(section.getByText("Editor: Operation Ledger (synthetic demo)")).toBeVisible();
    const box = (await section.boundingBox())!;
    const columns = page.locator(".home-columns > .home-column");
    expect(await columns.count()).toBe(2);
    const [left, right] = [(await columns.nth(0).boundingBox())!, (await columns.nth(1).boundingBox())!];
    expect(Math.abs(box.x - left.x)).toBeLessThan(2);
    expect(Math.abs(box.x + box.width - (right.x + right.width))).toBeLessThan(2);
    expect(box.y).toBeGreaterThanOrEqual(Math.max(left.y + left.height, right.y + right.height));
    expect(await page.locator(".home-column section[aria-labelledby='answers-for']").count()).toBe(0);
    const size = (selector: string) => section.locator(selector).first().evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
    const title = await size("h2");
    for (const sub of ["h3", "h4", "summary"]) expect(await size(sub)).toBeLessThan(title);
  });
}

test("every registered Needs you action has its own proving test case above", () => {
  assertAllCovered("NEEDS_YOU_ACTIONS", NEEDS_YOU_ACTIONS);
});
