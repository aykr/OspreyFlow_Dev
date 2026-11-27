import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The strict-policy run (slice GG5a; ADR-152 decision 8; the owner's ruling on GG5a's draft, questions 2 and 3 (a)): MapLibre
// under the page service's own security policy, in Chromium and WebKit. `map.spec.ts` starts its own server on a free port of
// the test's loopback, so no port is fixed and no stack, Valkey or deployment is touched.
//   npm run test:csp --workspace apps/pages
// It belongs to no tree: the map module is kept once for both (decision 6). I2's per-tree specs come with the first routed
// map page (GG5b).
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 120_000,
  workers: 1,
  // Results go to the machine's temporary folder, never into the checkout.
  outputDir: join(tmpdir(), "ospreyflow-pages-csp-results"),
  use: { locale: "en-GB", viewport: { width: 1000, height: 700 }, deviceScaleFactor: 1 },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
});
