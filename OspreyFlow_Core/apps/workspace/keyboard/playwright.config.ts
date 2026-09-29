import { defineConfig } from "@playwright/test";

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
    command: "npx vite --port 5185 --strictPort",
    port: 5185,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5185",
  },
});
