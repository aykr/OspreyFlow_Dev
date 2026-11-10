// @vitest-environment node
// Each lane's Playwright runs get their own vite and harness ports (CARRIES, 10 November 2026:
// admin's axe run waited while case's vite held 5184, and lanes wrote override configs). Every
// config below is loaded as two slots would load it, and their ports must never meet; with no slot
// (`main`, a checkout of the product alone) they are today's. The slot comes from
// `$OSPREY_PORTS_SLOT`, set by whatever starts the run (`apps/lanePorts.ts`).
//
// Not here, by design: `live/` serves on 5173 because it must be the demo's own port (its config
// says why), and `deck-capture/` is an owner-run capture whose page asks its tile server's port in
// browser code; neither is a lane's routine run.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { inLinkedWorktree, lanePort, slotOf } from "../../lanePorts";

const CONFIGS = [
  "../a11y/playwright.config.ts",
  "./playwright.config.ts",
  "../map-verify/playwright.config.ts",
  "../perf/playwright.config.ts",
  "../export-capture/playwright.config.ts",
  "../../harness/a11y/playwright.config.ts",
  "../../harness/keyboard/playwright.config.ts",
] as const;

/** Today's ports: what every config used before T2, and still uses with no slot. */
const TODAY = /\b(518[3-6]|519[1-4]|721[7-9]|7220)\b/;

type Server = { port?: number; url?: string; command?: string };
type Loaded = { webServer?: Server | Server[]; use?: { baseURL?: string } };

function portsOf(config: Loaded): number[] {
  const servers =
    config.webServer === undefined ? [] : [config.webServer].flat();
  const ports = new Set<number>();
  for (const server of servers) {
    if (server.port !== undefined) ports.add(Number(server.port));
    if (server.url !== undefined) ports.add(Number(new URL(server.url).port));
    for (const match of (server.command ?? "").matchAll(/--port[ =](\d+)/g)) {
      ports.add(Number(match[1]));
    }
  }
  if (config.use?.baseURL) ports.add(Number(new URL(config.use.baseURL).port));
  return [...ports].sort();
}

async function load(path: string, slot: string | undefined): Promise<number[]> {
  vi.resetModules();
  if (slot === undefined) delete process.env.OSPREY_PORTS_SLOT;
  else process.env.OSPREY_PORTS_SLOT = slot;
  const url = new URL(path, import.meta.url).href;
  const module = (await import(/* @vite-ignore */ url)) as { default: Loaded };
  return portsOf(module.default);
}

const saved = process.env.OSPREY_PORTS_SLOT;
afterEach(() => {
  if (saved === undefined) delete process.env.OSPREY_PORTS_SLOT;
  else process.env.OSPREY_PORTS_SLOT = saved;
});

describe("each lane's Playwright runs use ports of their own", () => {
  it.each(CONFIGS)("%s: two slots never share a port", async (path) => {
    const one = await load(path, "1");
    const two = await load(path, "2");
    expect(one.length).toBeGreaterThan(0);
    expect(
      one.filter((port) => two.includes(port)),
      `slot 1 ${one}, slot 2 ${two}`,
    ).toEqual([]);
  });

  it.each(CONFIGS)("%s: slot 0 is today's ports", async (path) => {
    const today = await load(path, "0");
    expect(
      today.every((port) => TODAY.test(String(port))),
      `${today}`,
    ).toBe(true);
  });

  it("a slot that is not a whole number is refused in words", async () => {
    await expect(load(CONFIGS[0], "case")).rejects.toThrow(
      /OSPREY_PORTS_SLOT=case .* whole number/,
    );
    expect(() => slotOf({ OSPREY_PORTS_SLOT: "-1" })).toThrow(/whole number/);
    expect(slotOf({ OSPREY_PORTS_SLOT: " 7 " })).toBe(7);
    expect(lanePort(5185, { OSPREY_PORTS_SLOT: "7" })).toBe(5885);
  });

  it("with no slot: the main checkout keeps today's; a linked worktree is refused in words", () => {
    expect(slotOf({}, () => false)).toBe(0);
    expect(() => slotOf({}, () => true)).toThrow(
      /linked worktree and OSPREY_PORTS_SLOT is not set/,
    );
    expect(slotOf({ OSPREY_PORTS_SLOT: "3" }, () => true)).toBe(3);
    expect(() =>
      slotOf({ OSPREY_PORTS_SLOT: "unlisted-admin-b" }, () => false),
    ).toThrow(/unlisted-admin-b is not a whole number.*lane_ports\.tsv/);
  });

  it("a linked worktree is told apart from the main checkout, on any branch or a detached head", () => {
    // The two shapes the independent review named: docs on d2b-scratch (not lane/<name>), and a gate's
    // detached head. Neither may pass as the main checkout.
    const git = (cwd: string, ...args: string[]) =>
      execFileSync("git", args, {
        cwd,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      });
    const root = mkdtempSync(join(tmpdir(), "lane-ports-"));
    const main = join(root, "main");
    execFileSync("git", ["init", "-q", "-b", "main", main]);
    writeFileSync(join(main, "f"), "x");
    git(main, "add", "f");
    git(
      main,
      "-c",
      "user.name=t",
      "-c",
      "user.email=t@example.invalid",
      "commit",
      "-qm",
      "x",
    );
    git(
      main,
      "worktree",
      "add",
      "-q",
      "-b",
      "d2b-scratch",
      join(root, "scratch"),
    );
    git(main, "worktree", "add", "-q", "--detach", join(root, "gate"));
    expect(inLinkedWorktree(main)).toBe(false);
    expect(inLinkedWorktree(join(root, "scratch"))).toBe(true);
    expect(inLinkedWorktree(join(root, "gate"))).toBe(true);
    expect(inLinkedWorktree(root)).toBe(false); // no git at all: not a worktree of anything
    expect(() =>
      slotOf({}, () => inLinkedWorktree(join(root, "gate"))),
    ).toThrow(/linked worktree/);
  });

  it("no spec or page beside a config names one of today's ports itself", () => {
    // A spec that kept a literal (keyboard.spec.ts's same-origin address, setup-screens.spec.ts's
    // install page) would point at another lane's server once its config moved.
    const here = dirname(fileURLToPath(import.meta.url));
    const found: string[] = [];
    for (const config of CONFIGS) {
      const folder = dirname(join(here, config));
      for (const file of readdirSync(folder)) {
        if (!/\.(ts|tsx)$/.test(file) || file === "playwrightPorts.test.ts")
          continue;
        const text = readFileSync(join(folder, file), "utf8")
          .split("\n")
          .filter(
            (line) =>
              !line.trim().startsWith("//") && !/^\s*(\*|\/\*)/.test(line),
          )
          .join("\n")
          .replace(/lanePort\(\d+\)/g, "")
          .replace(/\s\/\/\s.*$/gm, ""); // a trailing comment ("5193 on main") is not a port in use
        if (TODAY.test(text)) found.push(join(folder, file));
      }
    }
    expect(
      found,
      "use lanePort(<today's port>) from apps/lanePorts.ts",
    ).toEqual([]);
  });
});
