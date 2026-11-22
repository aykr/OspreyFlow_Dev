// Studio › Releases on the page, by keyboard alone, with scripts and without (slice IS5a; `CLAUDE.md` rule 13; ADR-152
// decision 12). The cases are the React screen's three (`apps/workspace/keyboard/ingest-studio.spec.ts`: export; check
// then import; replace own draft by Tab and Space) rebuilt for the page, plus the help panel keeping what was typed. Each
// runs twice: with scripts (SK1 to SK4), and with scripts switched off (SO1 to SO3), where the same task is done with the
// forms' own buttons.
//
// The page is the real pages server, started here on a free port with the in-memory store, the real assets built to a
// scratch folder and a fake Conduit that records every request and refuses what the real one refuses
// (`test/support/fakeConduit.ts`). No `page.mouse`, no `.click()`: a control is reached by Tab or focused and pressed with
// the keyboard. A folder is chosen in the system's own picker, which the page cannot drive: its files are set on the input
// as the picker sets them (Playwright takes a directory), and every step after is the keyboard's.
//
// What the folder case proves about a real browser: the multipart form a browser sends for a `webkitdirectory` input
// names each file by its path below the chosen folder (`webkitRelativePath`), so the page can rebuild the bundle's paths
// from the file names (`bundleFromFolder` does it from the same property). The fake Conduit receives the bundle the page
// built, so a browser that sent bare names would show as one file in place of two, here.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";
import type { BrowserContext, Download, Locator, Page } from "@playwright/test";

import { buildAssets } from "../scripts/assets.mjs";
import { MemorySessionStore } from "../server/sessionStore.js";
import { main } from "../server/start.js";
import type { Running } from "../server/start.js";
import { EXPORT_FILES, fakeConduit } from "../test/support/fakeConduit.js";
import type { FakeConduit, Person } from "../test/support/fakeConduit.js";
import { generateSecret } from "../test/support/secret.js";

const CASE = "case-harbour";
const DATASET = "harbour-extract";
const RIGHTS = ["edit_target_model", "publish_pipelines", "edit_pipelines", "accept_types"];

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

/** The pages server, with a fake Conduit that knows one person, on a free port. Nothing is written but a scratch folder. */
async function studio(over: Partial<Person> = {}): Promise<Studio> {
  const token = `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
  const me: Person = {
    token,
    rights: RIGHTS,
    roles: ["data_engineer"],
    cases: [
      {
        id: CASE,
        name: "Wing review",
        level: "author",
        created_at: "2026-11-01T09:00:00Z",
        created_by: "analyst-1",
        domains: [],
        datasets: ["Harbour prison extract (synthetic)"],
        dataset_ids: [DATASET],
      },
    ],
    ...over,
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

async function open(page: Page, s: Studio, path = `/studio/releases?case=${CASE}`): Promise<void> {
  await page.goto(`${s.base}/session/sign-in`);
  await page.goto(`${s.base}${path}`);
  await expect(page.getByRole("heading", { name: "Export" })).toBeVisible();
}

/** Presses a control with the keyboard: focused, then Enter (or Space). A disabled control takes neither, so it is waited for. */
async function press(target: Locator, key = "Enter"): Promise<void> {
  await expect(target).toBeEnabled();
  await target.focus();
  await target.page().keyboard.press(key);
}

/** Reaches a control by Tab alone, from where focus is, or says it cannot be reached. */
async function tabTo(page: Page, target: Locator, limit = 40): Promise<void> {
  for (let i = 0; i < limit; i += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement)) return;
  }
  throw new Error("the control is not reached by Tab");
}

/** A release folder: the folder's own name, then the files as the export wrote them. */
function releaseFolder(): string {
  const folder = join(mkdtempSync(join(tmpdir(), "ospreyflow-release-")), "bundle");
  mkdirSync(join(folder, "pipelines"), { recursive: true });
  writeFileSync(join(folder, "release.yaml"), "apiVersion: ospreyflow.io/v1\n");
  writeFileSync(join(folder, "pipelines", "visits.yaml"), "name: visits\n");
  return folder;
}

const importCalls = (s: Studio) => s.conduit.calls.filter((c) => c.path.endsWith("/release/import"));

test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

// ------------------------------------------------------------------------------------------------- with scripts

/**
 * A download that worked: named as the page names it, not failed, and holding the file's own text. A suggested name alone is
 * not proof (a link with a `download` attribute to a route that answers 404 still has one: it was shown red that way).
 */
async function savedAs(download: Download, name: string, text: string): Promise<void> {
  expect(download.suggestedFilename()).toBe(name);
  expect(await download.failure()).toBeNull();
  const saved = await download.path();
  expect(saved).not.toBeNull();
  expect(readFileSync(saved as string, "utf8")).toBe(text);
}

test.describe("with scripts", () => {
  test("SK1: a release is exported by keyboard, its files listed, and a file downloaded", async ({ page }) => {
    const s = await studio();
    try {
      await open(page, s);
      const version = page.getByLabel("Release version");
      await version.focus();
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.type("2");
      await press(page.getByRole("button", { name: "Export", exact: true }));
      await expect(page.getByText(/The release has 3 files\./)).toBeVisible();
      const sent = s.conduit.calls.find((c) => c.path === `/v1/datasets/${DATASET}/release`);
      expect(sent?.query.get("version")).toBe("2");
      const download = page.waitForEvent("download");
      await press(page.getByRole("link", { name: "model.yaml" }));
      await savedAs(await download, "model.yaml", EXPORT_FILES["model.yaml"]);
    } finally {
      await s.stop();
    }
  });

  test("SK2: a release is checked, then imported as drafts, by keyboard", async ({ page }) => {
    const s = await studio();
    try {
      await open(page, s);
      // Chosen in the picker; the page reads it as soon as it is chosen (an enhancement), and the paths are the browser's.
      await page.getByLabel("Choose the release's folder").setInputFiles(releaseFolder());
      await expect(page.getByText("Read 2 files from the folder.")).toBeVisible();
      await expect(page.getByRole("button", { name: "Import as drafts" })).toBeDisabled();
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByText("Would write Wing phone calls as a new draft.")).toBeVisible();
      await press(page.getByRole("button", { name: "Import as drafts" }));
      await expect(page.getByText("Everything imported is a draft. Make the model live in 1 Model when it is ready.")).toBeVisible();
      const imports = importCalls(s);
      expect(imports.map((c) => c.query.get("dry_run"))).toEqual(["true", "false"]);
      const files = (JSON.parse(imports[0]?.body ?? "{}") as { files: Record<string, string> }).files;
      expect(Object.keys(files).sort()).toEqual(["pipelines/visits.yaml", "release.yaml"]);
    } finally {
      await s.stop();
    }
  });

  test("SK3: an importer's own draft is replaced only once confirmed, by keyboard", async ({ page }) => {
    const s = await studio({ ownDraft: 3 });
    try {
      await open(page, s);
      await page.getByLabel("Choose the release's folder").setInputFiles(releaseFolder());
      await expect(page.getByText("Read 2 files from the folder.")).toBeVisible();
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByText(/your own in-progress draft/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Import as drafts" })).toBeDisabled();
      const confirm = page.getByRole("checkbox", { name: "Replace my draft of the domain model" });
      await tabTo(page, confirm);
      await expect(confirm).toBeFocused();
      await page.keyboard.press("Space");
      await expect(page.getByText("Would write Wing phone calls as the draft, in place of the one open now.")).toBeVisible();
      await expect(confirm).toBeChecked();
      await press(page.getByRole("button", { name: "Import as drafts" }));
      await expect(page.getByText("Everything imported is a draft. Make the model live in 1 Model when it is ready.")).toBeVisible();
      expect(s.conduit.written[0]?.replace).toBe("3");
    } finally {
      await s.stop();
    }
  });

  test("SK4: the help opens by keyboard and what was typed in the export form is still there", async ({ page }) => {
    const s = await studio();
    try {
      await open(page, s);
      const name = page.getByLabel("Release name");
      await name.focus();
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.type("typed-before-help");
      const help = page.locator("#studio-help summary");
      await tabTo(page, help).catch(async () => {
        // The panel is before the form in the page: reach it from the top of the page instead.
        await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
        await tabTo(page, help);
      });
      await page.keyboard.press("Enter");
      await expect(page.locator("#studio-help")).toHaveAttribute("open", "");
      await expect(page.getByText("data_engineer")).toBeVisible();
      await expect(name).toHaveValue("typed-before-help");
      expect(page.url()).toContain("/studio/releases"); // no navigation
    } finally {
      await s.stop();
    }
  });
});

// ------------------------------------------------------------------------------------------------- scripts off

test.describe("scripts off", () => {
  test.use({ javaScriptEnabled: false });

  test("SO1: a release is exported by keyboard with scripts off, and a file downloaded", async ({ page }) => {
    const s = await studio();
    try {
      await open(page, s);
      const version = page.getByLabel("Release version");
      await version.focus();
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.type("2");
      await press(page.getByRole("button", { name: "Export", exact: true }));
      await expect(page.getByText(/The release has 3 files\./)).toBeVisible();
      expect(s.conduit.calls.find((c) => c.path === `/v1/datasets/${DATASET}/release`)?.query.get("version")).toBe("2");
      const download = page.waitForEvent("download");
      await press(page.getByRole("link", { name: "model.yaml" }));
      await savedAs(await download, "model.yaml", EXPORT_FILES["model.yaml"]);
    } finally {
      await s.stop();
    }
  });

  test("SO2: a release folder is read, checked and imported with scripts off, by the forms' own buttons", async ({ page }) => {
    const s = await studio();
    try {
      await open(page, s);
      const input = page.getByLabel("Choose the release's folder");
      await input.setInputFiles(releaseFolder());
      // What the browser holds for each file: its path below the folder, which the form sends as the file's name.
      const held = await input.evaluate((el) => Array.from((el as HTMLInputElement).files ?? []).map((f) => f.webkitRelativePath).sort());
      expect(held).toEqual([expect.stringMatching(/^bundle\/pipelines\/visits\.yaml$/), expect.stringMatching(/^bundle\/release\.yaml$/)]);
      await press(page.getByRole("button", { name: "Read the folder" }));
      await expect(page.getByText("Read 2 files from the folder.")).toBeVisible();
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByText("Would write Wing phone calls as a new draft.")).toBeVisible();
      await press(page.getByRole("button", { name: "Import as drafts" }));
      await expect(page.getByText("Everything imported is a draft. Make the model live in 1 Model when it is ready.")).toBeVisible();
      const imports = importCalls(s);
      expect(imports.map((c) => c.query.get("dry_run"))).toEqual(["true", "false"]);
      const files = (JSON.parse(imports[0]?.body ?? "{}") as { files: Record<string, string> }).files;
      expect(Object.keys(files).sort()).toEqual(["pipelines/visits.yaml", "release.yaml"]);
    } finally {
      await s.stop();
    }
  });

  test("SO3: an importer's own draft is replaced only once confirmed, with scripts off: Tab and Space, then the button", async ({ page }) => {
    const s = await studio({ ownDraft: 3 });
    try {
      await open(page, s);
      await page.getByLabel("Choose the release's folder").setInputFiles(releaseFolder());
      await press(page.getByRole("button", { name: "Read the folder" }));
      await expect(page.getByText("Read 2 files from the folder.")).toBeVisible();
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByText(/your own in-progress draft/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Import as drafts" })).toBeDisabled();
      const confirm = page.getByRole("checkbox", { name: "Replace my draft of the domain model" });
      await tabTo(page, confirm);
      await page.keyboard.press("Space");
      await expect(confirm).toBeChecked();
      // With scripts off the tick does not check by itself: the button beside it does.
      await tabTo(page, page.getByRole("button", { name: "Check again, replacing my draft" }));
      await page.keyboard.press("Enter");
      await expect(page.getByText("Would write Wing phone calls as the draft, in place of the one open now.")).toBeVisible();
      await press(page.getByRole("button", { name: "Import as drafts" }));
      await expect(page.getByText("Everything imported is a draft. Make the model live in 1 Model when it is ready.")).toBeVisible();
      expect(s.conduit.written[0]?.replace).toBe("3");
    } finally {
      await s.stop();
    }
  });

  // Not one of Scenario S's rows: the same task as SO3 by the other way a person with scripts off may take it, which a
  // screen-reader user is most likely to (the button says what it does, so nothing else need be reached). The button alone
  // replaces the draft, and the main Check button after it keeps what was confirmed, as the React screen's `onCheck` does.
  test("scripts off: the button that says it replaces my draft does so on its own, and the next Check keeps it", async ({ page }) => {
    const s = await studio({ ownDraft: 3 });
    try {
      await open(page, s);
      await page.getByLabel("Choose the release's folder").setInputFiles(releaseFolder());
      await press(page.getByRole("button", { name: "Read the folder" }));
      await expect(page.getByText("Read 2 files from the folder.")).toBeVisible();
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByText(/your own in-progress draft/)).toBeVisible();
      await expect(page.getByRole("checkbox", { name: "Replace my draft of the domain model" })).not.toBeChecked();
      await press(page.getByRole("button", { name: "Check again, replacing my draft" }));
      await expect(page.getByText("Would write Wing phone calls as the draft, in place of the one open now.")).toBeVisible();
      expect(importCalls(s).at(-1)?.query.get("replace_own_draft")).toBe("3");
      await press(page.getByRole("button", { name: "Check the release" }));
      await expect(page.getByRole("checkbox", { name: "Replace my draft of the domain model" })).toBeChecked();
      expect(importCalls(s).at(-1)?.query.get("replace_own_draft")).toBe("3");
      await press(page.getByRole("button", { name: "Import as drafts" }));
      await expect(page.getByText("Everything imported is a draft. Make the model live in 1 Model when it is ready.")).toBeVisible();
      expect(s.conduit.written[0]?.replace).toBe("3");
    } finally {
      await s.stop();
    }
  });
});
