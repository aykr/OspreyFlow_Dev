// Studio › the dataset map on the page, by keyboard alone, with scripts and without (slice IS3; `CLAUDE.md` rule 13; ADR-152
// decision 12). The page is a read-only table in the Studio's frame: it adds no action of its own, so the case that proves it
// is the tab order through the whole page: every stop is a native one, in the page's own order, the table (which needs no
// script) is in the accessibility tree as a table with its four column headers and one row per pipeline, and the frame's
// dataset switch, the one control the page has, works from the keyboard on this path.
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
  const rows = table.getByRole("row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1).getByRole("rowheader")).toHaveText("Calls");
  await expect(rows.nth(1).getByRole("cell")).toHaveText(["draft", "v1", "Source, Map, Load"]);
  await expect(rows.nth(2).getByRole("rowheader")).toHaveText("Visits");
  await expect(rows.nth(2).getByRole("cell")).toHaveText(["deployed", "v3", "Source, Profile, Map, Load"]);
  await expect(page.getByText(/runs after/i)).toHaveCount(0);
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
