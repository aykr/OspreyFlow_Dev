import { expect, type Locator, type Page } from "@playwright/test";

/** Chooses a native select's option as a person does with it focused: by typing its label. A closed
 * select takes arrow keys differently by platform (macOS opens the menu), and letters typed within
 * about a second join into one search, so the label is typed whole after a pause (`keyboard.spec.ts`'s
 * `chooseOption`). The orchestrator's L2.10 review: never `selectOption` (rule 13), and one copy of
 * this for every spec that needs it. */
export async function chooseByTyping(page: Page, select: Locator, value: string) {
  await select.focus();
  const label = ((await select.locator(`option[value="${value}"]`).textContent()) ?? "").trim();
  if (label === "") throw new Error(`no option with value ${value}`);
  await page.waitForTimeout(1100);
  await page.keyboard.type(label);
  await expect(select).toHaveValue(value);
}
