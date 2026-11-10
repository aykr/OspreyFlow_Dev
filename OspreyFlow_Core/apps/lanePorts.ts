// Each lane's own ports for its Playwright runs (T2). A config asks `lanePort(<today's port>)` and
// gets that port plus 100 x `$OSPREY_PORTS_SLOT`, so two lanes' vite and harness servers never meet,
// on a developer's machine or on a test server where lanes' copies run side by side. The slot is
// given by whatever starts the run (the build tooling's lane launcher and its server runner, each
// from its own table of lanes). Core itself knows no lane and no table (ADR-114 decision 1).
//
// With no slot given: a repository's main checkout (and a copy that is not a linked worktree, as on
// CI) keeps today's ports, slot 0. A linked worktree is refused in words, since it is some lane's or
// some gate's and would silently share slot 0 with the main checkout: a branch that is not
// `lane/<name>`, or a detached head, says nothing about whose it is.
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const STEP = 100;

const HERE = dirname(fileURLToPath(import.meta.url));

/** Whether `cwd` is in a linked worktree (its git dir is not the common one); false with no git. */
export function inLinkedWorktree(cwd: string = HERE): boolean {
  try {
    const [gitDir, common] = execFileSync(
      "git",
      ["rev-parse", "--git-dir", "--git-common-dir"],
      {
        cwd,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      },
    )
      .trim()
      .split("\n")
      .map((path) => resolve(cwd, path.trim()));
    return gitDir !== undefined && common !== undefined && gitDir !== common;
  } catch {
    return false;
  }
}

/** The slot `$OSPREY_PORTS_SLOT` gives; 0 when unset outside a linked worktree; else refused. */
export function slotOf(
  env: NodeJS.ProcessEnv,
  linked: () => boolean = inLinkedWorktree,
): number {
  const given = env.OSPREY_PORTS_SLOT?.trim();
  if (!given) {
    if (!linked()) return 0;
    throw new Error(
      "this checkout is a linked worktree and OSPREY_PORTS_SLOT is not set, so its Playwright ports " +
        "would be the main checkout's and could meet another run's: export OSPREY_PORTS_SLOT=<the " +
        "lane's slot> (the lanes' table, scripts/lane_ports.tsv), as the lane launcher does.",
    );
  }
  if (!/^\d+$/.test(given)) {
    throw new Error(
      `OSPREY_PORTS_SLOT=${given} is not a whole number, so this run's Playwright ports cannot be ` +
        "told apart from another lane's: a lane not yet in the lanes' table " +
        "(scripts/lane_ports.tsv) needs its own row there.",
    );
  }
  return Number(given);
}

/** `base` moved to this run's own block. */
export function lanePort(
  base: number,
  env: NodeJS.ProcessEnv = process.env,
): number {
  return base + STEP * slotOf(env);
}
