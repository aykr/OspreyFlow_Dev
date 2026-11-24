// Studio › the dataset map on the page, by keyboard alone, with scripts and without (slice IS3, and IS6a's order form;
// `CLAUDE.md` rule 13; ADR-152 decision 12). The page is a table in the Studio's frame and, since IS6a, a form that sets the order
// pipelines run in. DK1 and DO1 prove the tab order through the whole page: every stop is a native one, in the page's own order
// (the frame's, then each pipeline's tick boxes, then the button that saves the order), the table (which needs no script) is in the
// accessibility tree as a table with its four column headers (no "Runs after" while no order is stored) and one row per pipeline,
// and the frame's dataset switch works from the keyboard on this path. DK2 and DO2 are the edit action's own case, end to end: a
// link is ticked with Space, Tab reaches Save the run order, Enter saves it, the Conduit holds version 1 and the page now has its
// fifth column. DK3 and DO3 save a cycle from the keyboard: the page says which pipelines are in it and the tick is still there.
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
import type { FakeConduit, Person } from "../test/support/fakeConduit.js";
import { generateSecret } from "../test/support/secret.js";

const CASE = "case-harbour";
const DATASET = "harbour-extract";
const NAME = "Harbour prison extract (synthetic)";
const RIGHTS = ["edit_target_model", "publish_pipelines", "edit_pipelines", "accept_types", "run_pipelines", "add_ingest_files"];
const PATH = `/studio/dataset-map?case=${CASE}`;

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

const graph = (kinds: string[]) => ({
  nodes: kinds.map((kind, i) => ({ id: `n${i}`, kind, label: kind, config: {} })),
  edges: kinds.slice(1).map((_, i) => ({ source: `n${i}`, target: `n${i + 1}` })),
});

/** The pages server, with a fake Conduit that knows one person who has two pipelines in the dataset, on a free port. */
async function studio(): Promise<Studio> {
  const token = `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
  const me: Person = {
    token,
    rights: RIGHTS,
    roles: ["data_engineer"],
    cases: [
      { id: CASE, name: "Wing review", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "analyst-1", domains: [], datasets: [NAME], dataset_ids: [DATASET] },
    ],
    pipelines: [
      { recipe_id: "r2", version: 1, status: "draft", label: "Calls", dataset_id: DATASET, pipeline: graph(["source", "map", "load"]) },
      { recipe_id: "r1", version: 3, status: "published", label: "Visits", dataset_id: DATASET, pipeline: graph(["source", "profile", "map", "load"]) },
    ],
  };
  const conduit = await fakeConduit([me]);
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

// What each stop is, in the page's own order. The table is not among them: reading a table is not an action.
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
  // The order form: one group of tick boxes for each pipeline (Calls, then Visits), each box named by its pipeline, then the button.
  "input: Visits",
  "input: Calls (not deployed)",
  "button: Save the run order",
];

test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

async function openMap(page: Page, s: Studio): Promise<void> {
  await page.goto(`${s.base}/session/sign-in`);
  await page.goto(`${s.base}${PATH}`);
  await expect(page.getByRole("table", { name: `Pipelines loading ${NAME}` })).toBeVisible();
}

async function proveTheMap(page: Page): Promise<void> {
  const table = page.getByRole("table", { name: `Pipelines loading ${NAME}` });
  await expect(table.getByRole("columnheader")).toHaveText(["Pipeline", "Status", "Version", "Stages"]);
  // No order stored: no fifth column, and no word of "runs after" in the table (the form's legends are the form's own).
  const rows = table.getByRole("row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1).getByRole("rowheader")).toHaveText("Calls");
  await expect(rows.nth(1).getByRole("cell")).toHaveText(["draft", "v1", "Source, Map, Load"]);
  await expect(rows.nth(2).getByRole("rowheader")).toHaveText("Visits");
  await expect(rows.nth(2).getByRole("cell")).toHaveText(["deployed", "v3", "Source, Profile, Map, Load"]);
  await expect(table.getByText(/runs after/i)).toHaveCount(0);
}

/** The order form's tick box: what `pipeline` runs after, named by the group it is in and by its own label. */
const box = (page: Page, pipeline: string, after: string) => page.getByRole("group", { name: `${pipeline} runs after` }).getByRole("checkbox", { name: after });

/**
 * The edit action, from the keyboard alone: Calls runs after Visits is ticked with Space, Tab goes on to the last box and then
 * to the button (the stops are native and in the page's order), and Enter saves it. The Conduit holds it, and the page now says
 * so and has its fifth column (the one a stored order draws).
 */
async function setTheOrder(page: Page, s: Studio): Promise<void> {
  await openMap(page, s);
  await box(page, "Calls", "Visits").focus();
  await page.keyboard.press("Space");
  await expect(box(page, "Calls", "Visits")).toBeChecked();
  await page.keyboard.press("Tab");
  expect(await focusedName(page)).toBe("input: Calls (not deployed)");
  await page.keyboard.press("Tab");
  expect(await focusedName(page)).toBe("button: Save the run order");
  await page.keyboard.press("Enter");
  await expect(page.getByText("The run order is saved as version 1.")).toBeVisible();
  const table = page.getByRole("table", { name: `Pipelines loading ${NAME}` });
  await expect(table.getByRole("columnheader")).toHaveText(["Pipeline", "Status", "Version", "Stages", "Runs after"]);
  const rows = table.getByRole("row");
  await expect(rows.nth(1).getByRole("cell")).toHaveText(["draft", "v1", "Source, Map, Load", "Visits"]);
  await expect(rows.nth(2).getByRole("cell")).toHaveText(["deployed", "v3", "Source, Profile, Map, Load", "Nothing"]);
  await expect(box(page, "Calls", "Visits")).toBeChecked();
  expect(s.conduit.orders.get(DATASET)).toMatchObject({ version: 1, runs_after: { r2: ["r1"] } });
}

/** A cycle, saved from the keyboard: refused in words naming its pipelines, nothing saved, and the tick is still there. */
async function refuseTheCycle(page: Page, s: Studio): Promise<void> {
  await box(page, "Visits", "Calls (not deployed)").focus();
  await page.keyboard.press("Space");
  await expect(box(page, "Visits", "Calls (not deployed)")).toBeChecked();
  await page.keyboard.press("Tab");
  expect(await focusedName(page)).toBe("button: Save the run order");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "would run after itself" })).toContainText("“Calls”, “Visits”");
  await expect(box(page, "Visits", "Calls (not deployed)")).toBeChecked();
  expect(s.conduit.orders.get(DATASET)).toMatchObject({ version: 1, runs_after: { r2: ["r1"] } });
}

test.describe("with scripts", () => {
  test("DK1: the page is read by Tab alone: every stop is a native one, in the page's own order, and the table is a table", async ({ page }) => {
    const s = await studio();
    try {
      await openMap(page, s);
      await proveTheMap(page);
      expect(await tabOrder(page)).toEqual(TAB_ORDER);
      // The one control the page has works by keyboard from this path: Enter on Switch dataset comes back to the same map.
      await page.getByRole("button", { name: "Switch dataset" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/studio/dataset-map\\?case=${CASE}`));
      await proveTheMap(page);
    } finally {
      await s.stop();
    }
  });
});

test.describe("with scripts (the order's edit action)", () => {
  test("DK2: the order is set by keyboard alone: Space ticks a link, Tab reaches Save the run order, Enter saves it", async ({ page }) => {
    const s = await studio();
    try {
      await setTheOrder(page, s);
    } finally {
      await s.stop();
    }
  });

  test("DK3: a cycle saved by keyboard is refused in words naming its pipelines, with the tick kept and nothing saved", async ({ page }) => {
    const s = await studio();
    try {
      await setTheOrder(page, s);
      await refuseTheCycle(page, s);
    } finally {
      await s.stop();
    }
  });
});

test.describe("with scripts switched off", () => {
  test.use({ javaScriptEnabled: false });

  test("DO1: the same page and the same stops with scripts switched off", async ({ page }) => {
    const s = await studio();
    try {
      await openMap(page, s);
      await proveTheMap(page);
      expect(await tabOrder(page)).toEqual(TAB_ORDER);
      await page.getByRole("button", { name: "Switch dataset" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/studio/dataset-map\\?case=${CASE}`));
      await proveTheMap(page);
    } finally {
      await s.stop();
    }
  });
});

test.describe("with scripts switched off (the order's edit action)", () => {
  test.use({ javaScriptEnabled: false });

  test("DO2: the same edit with scripts switched off: the form posts, the Conduit holds version 1, the page has its fifth column", async ({ page }) => {
    const s = await studio();
    try {
      await setTheOrder(page, s);
    } finally {
      await s.stop();
    }
  });

  test("DO3: the same refusal of a cycle with scripts switched off", async ({ page }) => {
    const s = await studio();
    try {
      await setTheOrder(page, s);
      await refuseTheCycle(page, s);
    } finally {
      await s.stop();
    }
  });
});
