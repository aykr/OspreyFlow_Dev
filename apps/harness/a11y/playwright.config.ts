import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The same two real scratch paths `keyboard/playwright.config.ts` already uses, for the same
// reason: this suite navigates the real `App`, wired to the real `harness.webapp` API, and must
// never touch this checkout's own real `osprey.yaml` or the owner's own real, gitignored
// real-data-exceptions file.
const SCRATCH_CONFIG = join(tmpdir(), `osprey-a11y-spec-${process.pid}.yaml`);
const SCRATCH_RDE = join(tmpdir(), `real-data-exceptions-a11y-spec-${process.pid}.yaml`);
const SCRATCH_OUT_ROOT = join(tmpdir(), `osprey-generated-a11y-spec-${process.pid}`);

// A fake `--apply-command` is not needed here — this suite never clicks Launch, only scans the
// DOM axe-core reaches without pressing it.

// Distinct from `keyboard/playwright.config.ts`'s own 5191/7217, so both suites can run
// concurrently (CI does) without a port collision.
const VITE_PORT = 5193;
const API_PORT = "7219";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  webServer: [
    {
      command: `npx vite --port ${VITE_PORT} --strictPort`,
      port: VITE_PORT,
      reuseExistingServer: !process.env.CI,
      cwd: "..",
      env: { HARNESS_API_PORT: API_PORT },
    },
    {
      command:
        `uv run python -m harness --host 127.0.0.1 --port ${API_PORT} ` +
        `--config ${SCRATCH_CONFIG} --real-data-exceptions ${SCRATCH_RDE} ` +
        `--out-root ${SCRATCH_OUT_ROOT}`,
      port: Number(API_PORT),
      reuseExistingServer: !process.env.CI,
      cwd: "../../..",
      env: { PYTHONPATH: ".:packages" },
    },
  ],
  use: {
    baseURL: `http://localhost:${VITE_PORT}`,
  },
});
