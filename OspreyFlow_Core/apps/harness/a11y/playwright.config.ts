import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

import { INSTALL_API_PORT, INSTALL_TOKEN, INSTALL_VITE_PORT } from "./installPage";

// The same two real scratch paths `keyboard/playwright.config.ts` already uses, for the same
// reason: this suite navigates the real `App`, wired to the real `harness.webapp` API, and must
// never touch this checkout's own real `osprey.yaml` or the owner's own real, gitignored
// real-data-exceptions file.
const SCRATCH_CONFIG = join(tmpdir(), `osprey-a11y-spec-${process.pid}.yaml`);
const SCRATCH_RDE = join(tmpdir(), `real-data-exceptions-a11y-spec-${process.pid}.yaml`);
const SCRATCH_OUT_ROOT = join(tmpdir(), `osprey-generated-a11y-spec-${process.pid}`);

const INSTALL_SCRATCH = join(tmpdir(), `osprey-install-a11y-spec-${process.pid}`);
const STUB_PYTHON = '#!/bin/sh\necho "stub $*"\n';

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
      reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
      cwd: "..",
      env: { HARNESS_API_PORT: API_PORT },
    },
    {
      command:
        `uv run python -m harness.webapp --host 127.0.0.1 --port ${API_PORT} ` +
        `--config ${SCRATCH_CONFIG} --real-data-exceptions ${SCRATCH_RDE} ` +
        `--out-root ${SCRATCH_OUT_ROOT}`,
      port: Number(API_PORT),
      reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
      cwd: "../../..",
      env: { PYTHONPATH: ".:packages" },
    },
    // The guided install page (`install-page.spec.ts`, step 9b), started as
    // `keyboard/playwright.config.ts` starts it: a scratch product folder whose `.venv/bin/python`
    // only echoes, so nothing is ever installed, and scratch draft and answers files.
    {
      command: `npx vite --port ${INSTALL_VITE_PORT} --strictPort`,
      port: INSTALL_VITE_PORT,
      reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
      cwd: "..",
      env: { HARNESS_API_PORT: INSTALL_API_PORT },
    },
    {
      command:
        `mkdir -p ${INSTALL_SCRATCH}/product/.venv/bin ${INSTALL_SCRATCH}/product/cli && ` +
        `printf '${STUB_PYTHON}' > ${INSTALL_SCRATCH}/product/.venv/bin/python && ` +
        `chmod +x ${INSTALL_SCRATCH}/product/.venv/bin/python && ` +
        `printf 'profile: local-lite\\n' > ${INSTALL_SCRATCH}/product/osprey.yaml && ` +
        `uv run python -m harness.install_page --product ${INSTALL_SCRATCH}/product ` +
        `--token ${INSTALL_TOKEN} --port ${INSTALL_API_PORT} ` +
        `--draft ${INSTALL_SCRATCH}/osprey.draft.yaml --answers ${INSTALL_SCRATCH}/install.yaml`,
      port: Number(INSTALL_API_PORT),
      reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
      cwd: "../../..",
      env: { PYTHONPATH: ".:packages:cli" },
    },
  ],
  use: {
    baseURL: `http://localhost:${VITE_PORT}`,
  },
});
