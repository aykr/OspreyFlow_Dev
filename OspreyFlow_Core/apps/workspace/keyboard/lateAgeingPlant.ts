// CO3e's proof plant for the overdue-days case (`admin.spec.ts`, "when promotions are overdue is set in
// Operations by keyboard"; GitHub run 46012575717, "Expected: 4, Received: 3"). Rule 15. It is test-side
// and does nothing unless `OSPREY_PLANT_LATE_AGEING=1`:
//
//   OSPREY_PLANT_LATE_AGEING=1 npm run test:keyboard --workspace apps/workspace -- admin.spec.ts -g overdue
//
// The page reads `operations/ageing` twice: on mount, and again when `/v1/me` answers, because
// `AdminPlace` then renders again with a new `api` object. Each answer sets the field to the server's
// number. The plant holds the second answer until ArrowUp has been pressed, so it lands just after the
// keypress, or for HELD_MS, so a case that waits for it before pressing still receives it. The answer is
// held on the network, so a wait on the response sees it no sooner than the page does.
import type { Page } from "@playwright/test";

const HELD_MS = 1_000;
const AGEING_PATH = "/v1/admin/operations/ageing";

/** Call after the harness's own `page.route`: the later route runs first and falls back to it. */
export async function plantLateAgeing(page: Page): Promise<void> {
  let reads = 0;
  let askedAgain!: () => void;
  let release!: () => void;
  const secondAsked = new Promise<void>((done) => (askedAgain = done));
  const released = new Promise<void>((done) => (release = done));
  let held = true;

  await page.route(`**${AGEING_PATH}`, async (route) => {
    if (++reads === 2) {
      askedAgain();
      await Promise.race([
        released,
        new Promise((done) => setTimeout(done, HELD_MS)),
      ]);
      held = false;
    }
    await route.fallback();
  });

  const press = page.keyboard.press.bind(page.keyboard);
  page.keyboard.press = async (key, options) => {
    await press(key, options);
    if (key !== "ArrowUp") return;
    await secondAsked;
    if (!held) return; // it has already gone: nothing is left to land after this keypress
    const answered = page.waitForResponse((response) =>
      response.url().endsWith(AGEING_PATH),
    );
    release();
    await (await answered).finished();
    // The page reads the body and draws it.
    await page.evaluate(() => new Promise((done) => setTimeout(done, 100)));
  };
}
