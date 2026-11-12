import { defineConfig } from "@playwright/test";

import { KEYBOARD_PORT } from "./ports";

const PORT = KEYBOARD_PORT; // this run's own (T2, ./ports.ts): 5185 on main

export default defineConfig({
  testDir: ".",
  // Phase 7 Stage 4's `registryCoverage.test.ts` (a Vitest test, `npm test`'s own fast tier, not
  // a browser walkthrough — see its own header) shares this directory for the first time.
  // Playwright's default `testMatch` picks up `*.test.ts` as readily as `*.spec.ts`, and Vitest's
  // `describe`/`it` are not this runner's globals — scoped here so the two suites never collide
  // over the same file.
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  webServer: {
    command: `node scripts/sync_govuk_assets.mjs && npx vite --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "..",
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
    // A date is typed as a British analyst types it, day first (ADR-146 Amendment 1). A date
    // field's order follows the browser process's own locale, not Playwright's `locale` (which
    // only emulates `navigator.language` and Intl): `alerts.spec.ts` already set `locale:
    // "en-GB"`, and GitHub's runner (C.UTF-8, so en-US) still read "01122026" as 12 January
    // (run 43198701543). Chromium on Linux takes its locale from LANGUAGE/LC_ALL/LANG, so the
    // browser is started with en_GB there; on macOS it follows the OS, already day first on the
    // Mac. `--lang` is Chromium's own switch, for the hosts that honour it.
    locale: "en-GB",
    launchOptions: {
      args: ["--lang=en-GB"],
      env: { ...process.env, LANGUAGE: "en_GB", LC_ALL: "en_GB.UTF-8", LANG: "en_GB.UTF-8" },
    },
  },
});
