// The GOV.UK tree's Admin People page by keyboard alone, with scripts on (slice AD3a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4;
// scenario AP8). The page is read-only and adds no action beyond two links, so the cases that prove it are the tab order through the
// whole page (every stop a native one, in the page's own order, the skip link first, the table with no stop of its own) and that each
// link does what it says when activated by Enter. No `page.mouse`, no `.click()`. The service is started in the case for the `govuk`
// tree, against a fixture Conduit that refuses what the real routes refuse (`../adminPeopleConduit.ts`) and knows the signed-in person.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { MANAGE_PEOPLE, account, adminConduit } from "../adminPeopleConduit.js";
import { MemorySessionStore } from "../../../server/sessionStore.js";
import { main } from "../../../server/start.js";
import type { Running } from "../../../server/start.js";
import { generateSecret } from "../../support/secret.js";
import { bearer } from "../../support/studioWorld.js";

/** The stops of the People page, in the page's own order: the skip link, the layout's sign-out, the link to Help, the way back. */
const PEOPLE_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: What each role and right lets a person do", "a: Back to Home"];

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

async function withPeople(run: (base: string) => Promise<void>): Promise<void> {
  const token = bearer();
  const conduit = await adminConduit({
    readers: [{ token, rights: [MANAGE_PEOPLE] }],
    people: [
      account({ id: "k-alex", username: "alex.example", name: "Alex Example", roles: ["analyst"] }),
      account({ id: "k-blake", username: "blake.sample", name: "Blake Sample", roles: ["osprey-admin"], enabled: false }),
    ],
  });
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: conduit.url,
      OSPREY_PAGES_PUBLIC_ORIGIN: "https://osprey.test",
    },
    io,
    {
      store: new MemorySessionStore(),
      host: "127.0.0.1",
      assets,
      identityProvider: {
        async signIn() {
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: token, refreshToken: "not-used", idpSessionExpiresAt: Date.now() + 3_600_000 };
        },
      },
    },
  );
  if (!running) throw new Error("the pages server did not start");
  try {
    await run(`http://127.0.0.1:${running.port}`);
  } finally {
    await running.stop();
    await conduit.stop();
  }
}

async function openPeople(page: import("@playwright/test").Page, base: string): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}/admin/people`);
}

test.describe("the Admin People page with scripts", () => {
  test("AK1: Tab reaches the skip link first, then the sign-out, the link to Help and the way back, in the page's order, and the table adds no stop", async ({ page }) => {
    await withPeople(async (base) => {
      await openPeople(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Admin: People");
      await expect(page.getByRole("table", { name: "People and their roles" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(PEOPLE_TAB_ORDER);
    });
  });

  test("AK2: the skip link takes focus to the main landmark, and Enter on each link goes where it says", async ({ page }) => {
    await withPeople(async (base) => {
      await openPeople(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#main$/);
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "What each role and right lets a person do" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/help$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
      await page.goBack();
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("AK3: the landmarks are there, and the people are a table a reader can move through by its headers", async ({ page }) => {
    await withPeople(async (base) => {
      await openPeople(page, base);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const table = page.getByRole("table", { name: "People and their roles" });
      await expect(table.getByRole("columnheader")).toHaveText(["Person", "Roles", "State"]);
      await expect(table.getByRole("rowheader")).toHaveText(["Alex Example", "Blake Sample"]);
    });
  });
});
