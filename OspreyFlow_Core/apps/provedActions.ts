// Which keyboard actions this Playwright run has proved (CO3e, 27 November 2026). The registries are
// declared in `packages/glass-shared/src/keyboard/actionRegistry.ts`; a spec calls `registerCovered`
// where it proves an action, and its last case calls `assertAllCovered`.
//
// The proofs are kept on disk, never in the worker's memory. Playwright replaces a worker after a
// failed case, so a set held in memory began again empty: the list then named actions proved in the
// replaced worker, and could not tell them from actions never proved (GitHub run 46012575717).
//
// **A run's own folder.** This module's default export is the run's `globalSetup`, which both keyboard
// configs name. Playwright calls it once, before any worker starts. It makes a new, empty folder
// (`mkdtemp`) and puts its path in `$OSPREY_PROVED_DIR`, which the workers inherit. It always
// overwrites that variable, so a folder left by an earlier run, or named by the caller's own
// environment, is never read. It removes the folder when the run ends. With no folder, both functions
// refuse in words: they never fall back to memory.
//
// It is here, beside `lanePorts.ts`, and not in the shared package: it needs `node:fs`, and that
// package goes into the browser bundle. `apps/workspace/keyboard/registryRestart.test.ts` holds it.
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FOLDER = "OSPREY_PROVED_DIR";

/** The run's `globalSetup`: a new folder for this run's proofs; returns its teardown. */
export default function provedActionsRun(): () => void {
  const folder = mkdtempSync(join(tmpdir(), "osprey-proved-actions-"));
  process.env[FOLDER] = folder;
  return () => rmSync(folder, { recursive: true, force: true });
}

function runFolder(): string {
  const folder = process.env[FOLDER];
  if (!folder || !existsSync(folder)) {
    throw new Error(
      `${FOLDER} names no folder, so no keyboard proof can be kept or read: run the spec under a ` +
        "Playwright config whose globalSetup is apps/provedActions.ts.",
    );
  }
  return folder;
}

// One empty file for each proved id, in a folder for each registry: a proof for one registry can never
// satisfy another's list, and two workers writing at once cannot spoil each other's.
const proofOf = (folder: string, registryName: string, id: string) =>
  join(folder, encodeURIComponent(registryName), encodeURIComponent(id));

export function registerCovered(registryName: string, id: string): void {
  const folder = runFolder();
  mkdirSync(join(folder, encodeURIComponent(registryName)), {
    recursive: true,
  });
  writeFileSync(proofOf(folder, registryName, id), "");
}

export function assertAllCovered(
  registryName: string,
  actions: readonly string[],
): void {
  const folder = runFolder();
  const missing = actions.filter(
    (id) => !existsSync(proofOf(folder, registryName, id)),
  );
  if (missing.length > 0) {
    throw new Error(
      `${registryName}: keyboard action(s) registered with no proving test case: ${missing.join(", ")}`,
    );
  }
}
