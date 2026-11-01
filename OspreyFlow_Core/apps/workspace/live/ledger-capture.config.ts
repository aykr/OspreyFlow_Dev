import { defineConfig } from "@playwright/test";

// Operation Ledger's monitoring week (A1 to A4; `DEMO_GUIDE.md` §8b; ADR-108 Amendment 5): screen
// captures of the **deployed** Glass at the deployment's own address, signed in through its
// identity provider as each demo persona, over the loaded synthetic Ledger case (rule 9). Not a
// test suite and never in CI: it needs a deployment with the `operation-ledger` pack installed, and
// `ledger-capture.spec.ts` skips itself unless `OSPREY_LEDGER_CAPTURE=1`. Run from `apps/workspace`,
// one named test at a time, in the order the prison demo folder's `CAPTURE_RUNBOOK_v4.md` gives:
//
//   OSPREY_LEDGER_CAPTURE=1 npx playwright test --config live/ledger-capture.config.ts -g "<one test>"
//
// `OSPREY_CAPTURE_ORIGIN` and `OSPREY_CAPTURE_ENV` pick the deployment (the GOV.UK one, for its
// brand); `OSPREY_LEDGER_CAPTURE_SCREENS` writes the shots somewhere other than the default folder.
// No web server: the Glass is the deployment's, served by its proxy.
export default defineConfig({
  testDir: ".",
  testMatch: /ledger-capture\.spec\.ts$/,
  timeout: 300_000,
  expect: { timeout: 60_000 },
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: process.env.OSPREY_CAPTURE_ORIGIN ?? "http://ospreyflow.localhost",
    // As the prison demo's captures: 1440 by 900 at 100%, drawn at twice the pixels for slides.
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  },
});
