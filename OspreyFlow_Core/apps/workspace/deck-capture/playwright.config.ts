import { defineConfig } from "@playwright/test";

// The deck's capture rig — not a test suite and never in CI (`make ci` runs `test:keyboard`; this
// has its own script). Photographs the real components over the synthetic Operation Ledger
// fixture (rule 9) at the deck's own resolution; `fraud.capture.ts` writes the JPEGs straight
// into `OspreyFlow_deck_screens/`.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.capture\.ts$/,
  timeout: 120_000,
  workers: 1,
  webServer: [
    {
      command: "npx vite --port 5187 --strictPort",
      port: 5187,
      reuseExistingServer: !process.env.CI,
      cwd: "..",
    },
    {
      // The GB basemap build (tier 1, gitignored data), served with ranges and CORS for the map
      // harness; `fraud.capture.ts` fulfils the style's same-origin glyph reads from disk.
      command: "npx http-server . -p 5188 --cors -s",
      port: 5188,
      reuseExistingServer: !process.env.CI,
      // Playwright resolves this against the config's own directory, which `npx http-server`'s
      // relative root argument does not reliably survive.
      cwd: "../../../../OspreyFlow_Data/basemap",
    },
  ],
  use: {
    baseURL: "http://localhost:5187",
    viewport: { width: 1512, height: 807 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  },
});
