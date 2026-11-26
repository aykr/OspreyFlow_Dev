import { defineConfig } from "@playwright/test";

import keyboard from "./playwright.config";

// The canvas-look comparison (`canvas-compare.spec.ts`, slice WS4a) on its own, with the keyboard suite's server and
// browser settings: `npm run test:canvas-compare`. Kept out of `test:keyboard` (its `testIgnore`) because its
// references belong to one renderer and were made on the server's build account, not on CI's runner: it joins CI as
// its own step once a CI run has shown it green there (the owner's diff, `WS4a_diffs/COMPARE_CI.diff`), as
// `map-verify`'s pictures wait for Linux references (`ci.yml`).
export default defineConfig({
  ...keyboard,
  testIgnore: undefined,
  testMatch: /canvas-compare\.spec\.ts$/,
});
