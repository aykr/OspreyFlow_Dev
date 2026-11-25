/**
 * What the GOV.UK tree's Playwright cases share (slice GR2a): the pages service started for the `govuk` tree in the test itself, the
 * front proxy's word that the request came over TLS (the session cookie is `Secure`), and the tab order read off the page. No Conduit
 * is needed: the Help page asks it nothing, so the service is started with no address for one.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import type { BrowserContext, Page } from "@playwright/test";

import { buildAssets } from "../../scripts/assets.mjs";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { generateSecret } from "../support/secret.js";

export interface Assets {
  dir: string;
  manifest: Record<string, string>;
}

/** The real stylesheet, built once to a scratch folder, so that focus is drawn as it is in a deployment. */
export async function buildScratchAssets(): Promise<Assets> {
  const dir = mkdtempSync(join(tmpdir(), "ospreyflow-pages-govuk-assets-"));
  const built = await buildAssets({ outDir: dir });
  return { dir, manifest: built.manifest };
}

export interface Govuk {
  base: string;
  stop(): Promise<void>;
}

/** The service for the `govuk` tree, on a free port, signing in as a person who holds no right at all. */
export async function startGovuk(assets: Assets): Promise<Govuk> {
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    { OSPREY_PAGES_PORT: "0", OSPREY_PAGES_SESSION_SECRET: generateSecret(48), OSPREY_PAGES_TREE: "govuk" },
    io,
    {
      store: new MemorySessionStore(),
      host: "127.0.0.1",
      assets,
      identityProvider: {
        async signIn() {
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: "not-used", refreshToken: "not-used", idpSessionExpiresAt: Date.now() + 3_600_000 };
        },
      },
    },
  );
  if (!running) throw new Error("the pages server did not start");
  return { base: `http://127.0.0.1:${running.port}`, stop: () => running.stop() };
}

/** The front proxy says the request came over TLS, as it does in a deployment; the session cookie is `Secure`. */
export async function viaProxy(context: BrowserContext): Promise<void> {
  await context.route("**/*", (route) => route.continue({ headers: { ...route.request().headers(), "x-forwarded-proto": "https" } }));
}

/** Signs in through the real route, then opens the Help page. */
export async function openHelp(page: Page, base: string): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}/help`);
}

/** What the focused element is called, for the tab order: its accessible name or its text. */
async function focusedName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return "(page)";
    const label = el.getAttribute("aria-label") ?? el.textContent ?? "";
    return `${el.tagName.toLowerCase()}: ${label.replace(/\s+/g, " ").trim()}`;
  });
}

/** Tab through the whole page once, and say what each stop was, until focus leaves the page's last stop. */
export async function tabOrder(page: Page): Promise<string[]> {
  const seen: string[] = [];
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    const name = await focusedName(page);
    if (name === "(page)" || seen.includes(name)) break;
    seen.push(name);
  }
  return seen;
}

/** The stops of the Help page, in the page's own order: the skip link, the layout's sign-out, a link to each section, the way back. */
export const HELP_TAB_ORDER: string[] = [
  "a: Skip to main content",
  "button: Sign out",
  "a: The places",
  "a: Roles",
  "a: Your level in a case",
  "a: Teams, leads and Authors",
  "a: What each right lets you do",
  "a: Back to Home",
];
