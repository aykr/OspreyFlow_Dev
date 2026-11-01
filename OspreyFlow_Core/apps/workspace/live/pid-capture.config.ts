import { defineConfig } from "@playwright/test";

// The Prison Intelligence demo's screen captures (Brief 3 Part C): the **deployed** Glass at the
// deployment's own address, signed in through its identity provider as each demo persona, over
// the loaded synthetic PID case (rule 9). Not a test suite and never in CI: it needs the owner's
// deployment up with the pack installed, and `pid-capture.spec.ts` skips itself unless
// `OSPREY_PID_CAPTURE=1`. Run from `apps/workspace`:
//
//   OSPREY_PID_CAPTURE=1 npx playwright test --config live/pid-capture.config.ts -g "<one test>"
//
// One named test at a time (`-g`), never the whole file on a deployment the owner uses: several
// tests change the case's state as the presenter would (a hotlist, a load, a rule, a close, a pack
// item). The order and the state each test needs are in the demo folder's `CAPTURE_RUNBOOK_v4.md`.
// `OSPREY_PID_CAPTURE_ORIGIN` and `OSPREY_PID_CAPTURE_ENV` pick the deployment (the GOV.UK one, for
// its brand); `OSPREY_PID_CAPTURE_SCREENS` writes the shots to another folder than `screens/`.
//
// No web server: the Glass is the deployment's, served by its proxy.
export default defineConfig({
  testDir: ".",
  testMatch: /pid-capture\.spec\.ts$/,
  timeout: 300_000,
  expect: { timeout: 60_000 },
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: process.env.OSPREY_PID_CAPTURE_ORIGIN ?? "http://ospreyflow.localhost",
    // The brief's 1440 by 900 at 100% zoom; drawn at twice the pixels so a slide stays sharp.
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  },
});
