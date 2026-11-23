// Studio › the Model step on the page, by keyboard alone, with scripts and without (slice IS2a; `CLAUDE.md` rule 13; ADR-152
// decision 12). The page's actions are forms: a save and a discard, each a native button reached by Tab and pressed with Enter,
// beside the pack fields a person types in. The cases prove it end to end: the tab order through the whole page (every stop is
// a native one, in the page's own order), a save made from the keyboard (type a pin, Tab to Save draft, Enter) and a discard
// made the same way, each carried out by the Conduit; and a stale save, where the draft changed between reading the page and
// pressing Enter, which says the copy was out of date and keeps what was typed in the field.
//
// The page is the real pages server, started here on a free port with the in-memory store, the real assets built to a scratch
// folder and a fake Conduit that records every request and refuses what the real one refuses (`test/support/fakeConduit.ts`).
// No `page.mouse`, no `.click()`.
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

import { buildAssets } from "../scripts/assets.mjs";
import { MemorySessionStore } from "../server/sessionStore.js";
import { main } from "../server/start.js";
import type { Running } from "../server/start.js";
import { fakeConduit } from "../test/support/fakeConduit.js";
import type { FakeConduit, FakeModel, Person } from "../test/support/fakeConduit.js";
import { generateSecret } from "../test/support/secret.js";

const CASE = "case-harbour";
const DATASET = "harbour-extract";
const NAME = "Harbour prison extract (synthetic)";
const ME = "alice-1";
const RIGHTS = ["edit_target_model", "publish_pipelines", "edit_pipelines", "accept_types", "run_pipelines", "add_ingest_files"];
const PATH = `/studio/model?case=${CASE}`;
const DRAFT_TABLE = `Types in the draft of ${NAME}`;

let assets: { dir: string; manifest: Record<string, string> };

test.beforeAll(async () => {
  const dir = mkdtempSync(join(tmpdir(), "ospreyflow-pages-assets-"));
  const built = await buildAssets({ outDir: dir });
  assets = { dir, manifest: built.manifest };
});

interface Studio {
  base: string;
  conduit: FakeConduit;
  stop(): Promise<void>;
}

const VESSEL = {
  name: "Vessel",
  kind: "entity_type",
  on_type: null,
  added_in: 1,
  retired_in: null,
  pole_class: "object",
  identifiers: ["imo_number"],
  matching: { match_on: "imo_number", on_match: "reference" },
  value_type: null,
  indexed: false,
};

const draft = (over: Partial<FakeModel> = {}): FakeModel => ({
  dataset_id: DATASET,
  version: 2,
  state: "draft",
  packs: { niem: 3 },
  extensions: [VESSEL],
  reference_lists: [],
  created_at: "2026-11-20T09:30:00Z",
  created_by: ME,
  made_live_at: null,
  made_live_by: null,
  reverted_from: null,
  revision: "rev-seed",
  ...over,
});

/** The pages server, with a fake Conduit that knows one person who holds a draft of the dataset's model, on a free port. */
async function studio(): Promise<Studio> {
  const token = `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
  const me: Person = {
    token,
    id: ME,
    rights: RIGHTS,
    roles: ["data_engineer"],
    cases: [
      { id: CASE, name: "Wing review", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "analyst-1", domains: [], datasets: [NAME], dataset_ids: [DATASET] },
    ],
  };
  const conduit = await fakeConduit([me]);
  conduit.models.set(DATASET, { live: draft({ version: 1, state: "live", packs: {}, extensions: [], made_live_at: "2026-11-01T10:00:00Z", made_live_by: "sys-1" }), draft: draft() });
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
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
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: token, refreshToken: `r-${token}`, idpSessionExpiresAt: Date.now() + 3_600_000 };
        },
      },
    },
  );
  if (!running) throw new Error("the pages server did not start");
  return {
    base: `http://127.0.0.1:${running.port}`,
    conduit,
    stop: async () => {
      await running.stop();
      await conduit.stop();
    },
  };
}

/** The front proxy says the request came over TLS, as it does in a deployment; the session cookie is `Secure`. */
async function viaProxy(context: BrowserContext): Promise<void> {
  await context.route("**/*", (route) => route.continue({ headers: { ...route.request().headers(), "x-forwarded-proto": "https" } }));
}

/** What the focused element is called, for the tab order: its accessible name or its text. */
async function focusedName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return "(page)";
    const label = el.getAttribute("aria-label") ?? (el as HTMLInputElement).labels?.[0]?.textContent ?? el.textContent ?? "";
    return `${el.tagName.toLowerCase()}: ${label.replace(/\s+/g, " ").trim()}`;
  });
}

/** Tab through the whole page once, and say what each stop was, until focus leaves the page's last stop. */
async function tabOrder(page: Page): Promise<string[]> {
  const seen: string[] = [];
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    const name = await focusedName(page);
    if (name === "(page)" || seen.includes(name)) break;
    seen.push(name);
  }
  return seen;
}

const PIN = (label: string): string => `input: Version of the ${label} pack (leave blank to leave it out)`;

// What each stop is, in the page's own order. The tables are not among them: reading a table is not an action.
const TAB_ORDER: string[] = [
  "a: Skip to main content",
  "button: Sign out",
  `select: Dataset ${NAME}`,
  "button: Switch dataset",
  "summary: Roles, teams and Authors",
  "a: 1 Model",
  "a: 2 Sources",
  "a: 3 Pipelines",
  "a: 4 Runs",
  "a: 5 Releases",
  PIN("Financial fraud and AML (FIBO)"),
  PIN("Crime case analysis (NIEM)"),
  PIN("Cyber threat analytics (STIX 2.1)"),
  "button: Save draft",
  "button: Discard draft",
];

test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

async function openModel(page: Page, s: Studio): Promise<void> {
  await page.goto(`${s.base}/session/sign-in`);
  await page.goto(`${s.base}${PATH}`);
  await expect(page.getByRole("table", { name: DRAFT_TABLE })).toBeVisible();
}

async function proveTheTables(page: Page): Promise<void> {
  const table = page.getByRole("table", { name: DRAFT_TABLE });
  await expect(table.getByRole("columnheader")).toHaveText(["Type", "Class", "Identifiers", "Matching rule", "Properties"]);
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(table.getByRole("rowheader")).toHaveText("Vessel");
  await expect(table.getByRole("cell")).toHaveText(["Object", "imo_number", "Matches on imo_number: an existing record is used", "None"]);
}

/** Type a pin and save it, then discard the draft, by keyboard alone: the Conduit carries out what the keys asked for. */
async function saveThenDiscard(page: Page, s: Studio): Promise<void> {
  // Focus the NIEM pin by Tab from the Model place's last link: no pointer, no focus() call.
  await page.getByRole("link", { name: "5 Releases" }).focus();
  await page.keyboard.press("Tab"); // FIBO
  await page.keyboard.press("Tab"); // NIEM
  expect(await focusedName(page)).toBe(PIN("Crime case analysis (NIEM)"));
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("7");
  await page.keyboard.press("Tab"); // STIX
  await page.keyboard.press("Tab"); // Save draft
  expect(await focusedName(page)).toBe("button: Save draft");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Draft saved as version 2. Nothing that runs has changed.");
  expect(s.conduit.models.get(DATASET)?.draft?.packs).toEqual({ niem: 7 });
  expect(s.conduit.models.get(DATASET)?.draft?.extensions).toEqual([VESSEL]); // the save did not lose the draft's own type
  await proveTheTables(page);

  // Discard by keyboard: Tab from the NIEM pin to Save draft, then to Discard draft; Enter.
  await page.getByRole("button", { name: "Save draft" }).focus();
  await page.keyboard.press("Tab");
  expect(await focusedName(page)).toBe("button: Discard draft");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Draft discarded. Nothing that runs has changed.");
  expect(s.conduit.models.get(DATASET)?.draft).toBeNull();
  await expect(page.getByRole("button", { name: "Open a draft" })).toBeVisible();
}

/** A stale save: the draft changed after the page was read; Enter on Save draft is refused, and what was typed is still there. */
async function staleSave(page: Page, s: Studio): Promise<void> {
  const current = s.conduit.models.get(DATASET);
  if (!current) throw new Error("no model seeded");
  await page.getByRole("link", { name: "5 Releases" }).focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab"); // NIEM
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("9");
  // Meanwhile their draft was made live and a later one opened.
  s.conduit.models.set(DATASET, { live: current.draft, draft: draft({ version: 3 }) });
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab"); // Save draft
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toContainText("Your copy of the draft was out of date: it is now version 3. Nothing was saved.");
  await expect(page.getByLabel(/Crime case analysis \(NIEM\)/)).toHaveValue("9");
  expect(s.conduit.models.get(DATASET)?.draft?.packs).toEqual({ niem: 3 });
}

test.describe("with scripts", () => {
  test("MK1: the page is read by Tab alone: every stop is a native one, in the page's own order, and the types are a table", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await proveTheTables(page);
      expect(await tabOrder(page)).toEqual(TAB_ORDER);
    } finally {
      await s.stop();
    }
  });

  test("MK2: a pin is typed, saved and the draft discarded by keyboard, each carried out by the Conduit", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await saveThenDiscard(page, s);
    } finally {
      await s.stop();
    }
  });

  test("MK3: a stale save by keyboard says the copy was out of date and keeps what was typed", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await staleSave(page, s);
    } finally {
      await s.stop();
    }
  });
});

test.describe("with scripts switched off", () => {
  test.use({ javaScriptEnabled: false });

  test("MO1: the same page and the same stops with scripts switched off", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await proveTheTables(page);
      expect(await tabOrder(page)).toEqual(TAB_ORDER);
    } finally {
      await s.stop();
    }
  });

  test("MO2: save and discard by keyboard with scripts switched off", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await saveThenDiscard(page, s);
    } finally {
      await s.stop();
    }
  });

  test("MO3: a stale save by keyboard with scripts switched off says so and keeps what was typed", async ({ page }) => {
    const s = await studio();
    try {
      await openModel(page, s);
      await staleSave(page, s);
    } finally {
      await s.stop();
    }
  });
});
