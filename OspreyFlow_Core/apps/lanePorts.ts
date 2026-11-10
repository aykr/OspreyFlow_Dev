// Each lane's own ports for its local Playwright runs (T2; `OspreyFlow_Build/scripts/lane_ports.tsv`
// has the table and the rule). A config asks `lanePort(<today's port>)` and gets that port plus
// 100 x its lane's slot, so two lanes' vite and harness servers never meet on this machine.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const TABLE = join(
  HERE,
  "..",
  "..",
  "OspreyFlow_Build",
  "scripts",
  "lane_ports.tsv",
);
export const STEP = 100;

/** lane -> slot, from the table's text. */
export function parseTable(text: string): Map<string, number> {
  const slots = new Map<string, number>();
  for (const line of text.split("\n")) {
    if (line.startsWith("#") || line.trim() === "") continue;
    const [lane, slot] = line.split("\t");
    if (lane && slot !== undefined) slots.set(lane.trim(), Number(slot));
  }
  return slots;
}

function branch(): string | null {
  try {
    return execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
      cwd: HERE,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

/**
 * This run's lane: $OSPREY_LANE, else $OSPREY_PORTS_LANE (set by `stack_lease.sh` for every run on
 * the test server, whose copies have no git and run side by side), else the `lane/<name>` branch;
 * null for main or no lane.
 */
export function laneOf(
  env: NodeJS.ProcessEnv,
  head: string | null,
): string | null {
  const named = (env.OSPREY_LANE || env.OSPREY_PORTS_LANE)?.trim();
  if (named) return named === "main" ? null : named;
  return head?.startsWith("lane/") ? head.slice("lane/".length) : null;
}

/** The lane's slot: its own row, or the longest row its name extends (`admin-ddl` is `admin`'s). */
export function slotOf(
  lane: string | null,
  table: Map<string, number> | null,
): number {
  if (lane === null || table === null) return 0;
  const exact = table.get(lane);
  if (exact !== undefined) return exact;
  const parent = [...table.keys()]
    .filter((name) => lane.startsWith(`${name}-`))
    .sort((a, b) => b.length - a.length)[0];
  if (parent !== undefined) return table.get(parent) as number;
  throw new Error(
    `lane "${lane}" has no row in ${TABLE} (lane_ports.tsv), so its Playwright ports could meet ` +
      `another lane's: add "${lane}<TAB><the next free slot>" there.`,
  );
}

/** `base` moved to this run's lane's own block. */
export function lanePort(
  base: number,
  env: NodeJS.ProcessEnv = process.env,
): number {
  const table = existsSync(TABLE)
    ? parseTable(readFileSync(TABLE, "utf8"))
    : null;
  const named = env.OSPREY_LANE || env.OSPREY_PORTS_LANE;
  return base + STEP * slotOf(laneOf(env, named ? null : branch()), table);
}
