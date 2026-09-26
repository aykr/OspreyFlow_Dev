import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// A scratch `osprey.yaml`, not this checkout's real one — `harness.webapp`'s own `Save` actions
// really write to disk, and this suite must never touch the repository's own committed config.
const SCRATCH_CONFIG = join(tmpdir(), `osprey-keyboard-spec-${process.pid}.yaml`);

// A scratch real-data-exceptions file — the Governance screen's own exceptions panel really
// reads/writes disk too, and `--real-data-exceptions`'s own default is
// `scripts.real_data_exceptions.CONFIG_PATH`, the owner's real, gitignored local file. Never
// touch that one from a test (`CLAUDE.md` rule 9 / ADR-035 §C3 / STANDING.md).
const SCRATCH_RDE = join(tmpdir(), `real-data-exceptions-keyboard-spec-${process.pid}.yaml`);

// A scratch `deploy/generated/` — the Preflight screen's own `Generate` really writes to disk,
// and `--out-root`'s own default is this checkout's real `deploy/generated/` (gitignored, but
// still real state a test run must not touch — the same reasoning as the two scratch paths
// above).
const SCRATCH_OUT_ROOT = join(tmpdir(), `osprey-generated-keyboard-spec-${process.pid}`);

// Not port 7000, `05_DEPLOYMENT.md` §2's own real default — `vite.config.ts`'s own module
// docstring has the reason: it collides with macOS's AirPlay Receiver on a real development
// machine, which answered every proxied request with its own 403 while `reuseExistingServer`
// quietly never started this suite's own server at all. A scratch port for a scratch server.
const API_PORT = "7217";

// `--apply-command`'s own real seam (`harness/webapp.py`'s own docstring) — a real, if tiny,
// subprocess standing in for `python -m harness.apply`, so a keyboard-driven Launch click proves
// the plumbing (Launch is really wired to a real subprocess, streamed) without a real Docker
// build. Double-quoted Python string literals only, on purpose: the whole JSON array is wrapped
// in single quotes for the shell below, and a raw `'` inside it would break out of that.
const FAKE_APPLY_COMMAND = JSON.stringify([
  "python3",
  "-c",
  'print("apply: local-lite ready in 1s"); print("  the Glass:   http://127.0.0.1:8080/")',
]);

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  webServer: [
    {
      command: "npx vite --port 5191 --strictPort",
      port: 5191,
      reuseExistingServer: !process.env.CI,
      cwd: "..",
      env: { HARNESS_API_PORT: API_PORT },
    },
    {
      // The real Python HTTP layer this app calls — not a stub. `--host 127.0.0.1` matches R2's
      // own loopback default; `vite.config.ts`'s own dev proxy forwards `/api`/`/admin` here.
      // `uv run`, the same invocation `ci.yml`'s own jobs already use, rather than a bare
      // `python`, which this repo's own convention never assumes is the right interpreter.
      command:
        `uv run python -m harness --host 127.0.0.1 --port ${API_PORT} ` +
        `--config ${SCRATCH_CONFIG} --real-data-exceptions ${SCRATCH_RDE} ` +
        `--out-root ${SCRATCH_OUT_ROOT} --apply-command '${FAKE_APPLY_COMMAND}'`,
      port: Number(API_PORT),
      reuseExistingServer: !process.env.CI,
      cwd: "../../..",
      env: { PYTHONPATH: ".:packages" },
    },
  ],
  use: {
    baseURL: "http://localhost:5191",
  },
});
