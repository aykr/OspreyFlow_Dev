// The browser's part of the two websites' checks (ospreyflow.org and ospreyflow.net): the theme switch, the animations'
// player, reduced motion, off screen, keyboard and accessibility scans in both themes. `tests/test_sites.py` and
// `tests/test_sites_design.py` hold everything a file can show; this holds what only a browser can.
//
// It lives beside the sites, not in OspreyFlow_Core (the product, published on its own: the orchestrator, 13 November
// 2026), and borrows Core's installed Playwright and axe-core by path. Run it from OspreyFlow_Build with
// `make sites-check` (`process/lanes/docs/sites2-make.diff`), or:
//
//   NODE_PATH=../OspreyFlow_Core/node_modules ../OspreyFlow_Core/node_modules/.bin/playwright test \
//     -c marketing_site/check/playwright.config.ts
//
// SITES_DIR serves another copy of the two sites (a red-first run against a planted defect); SITES_CHECK_PORT moves
// the server off 4719.
import { resolve } from "node:path";

import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.SITES_CHECK_PORT ?? 4719);
const SITES = resolve(__dirname, process.env.SITES_DIR ?? "../sites");

export default defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.ts",
  fullyParallel: true,
  retries: 0,
  reporter: [["list"]],
  outputDir: resolve(require("node:os").tmpdir(), `ospreyflow-sites-check-${process.pid}`),
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1280, height: 800 },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: `python3 -m http.server ${PORT} --bind 127.0.0.1 --directory "${SITES}"`,
    url: `http://127.0.0.1:${PORT}/org/index.html`,
    reuseExistingServer: false,
    stdout: "ignore",
    stderr: "ignore",
    timeout: 20_000,
  },
});
