// @vitest-environment node
// Each lane's local Playwright runs get their own vite and harness ports (CARRIES, 10 November
// 2026: admin's axe run waited while case's vite held 5184, and lanes wrote override configs).
// Every config below is loaded as two lanes would load it, and their ports must never meet; slot 0
// (`main`, the orchestrator, a checkout with no lane) keeps today's ports.
//
// Not here, by design: `live/` serves on 5173 because it must be the demo's own port (its config
// says why), and `deck-capture/` is an owner-run capture whose page asks its tile server's port in
// browser code; neither is a lane's routine run.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { laneOf, parseTable, slotOf, STEP, TABLE } from "../../lanePorts";

const CONFIGS = [
  "../a11y/playwright.config.ts",
  "./playwright.config.ts",
  "../map-verify/playwright.config.ts",
  "../perf/playwright.config.ts",
  "../export-capture/playwright.config.ts",
  "../../harness/a11y/playwright.config.ts",
  "../../harness/keyboard/playwright.config.ts",
] as const;

type Server = { port?: number; url?: string; command?: string };
type Loaded = { webServer?: Server | Server[]; use?: { baseURL?: string } };

function portsOf(config: Loaded): number[] {
  const servers =
    config.webServer === undefined ? [] : [config.webServer].flat();
  const ports = new Set<number>();
  for (const server of servers) {
    if (server.port !== undefined) ports.add(Number(server.port));
    if (server.url !== undefined) ports.add(Number(new URL(server.url).port));
    for (const match of (server.command ?? "").matchAll(
      /--port[ =]\$?\{?(\d+)/g,
    )) {
      ports.add(Number(match[1]));
    }
  }
  if (config.use?.baseURL) ports.add(Number(new URL(config.use.baseURL).port));
  return [...ports].sort();
}

async function load(path: string, lane: string | undefined): Promise<number[]> {
  vi.resetModules();
  if (lane === undefined) delete process.env.OSPREY_LANE;
  else process.env.OSPREY_LANE = lane;
  const url = new URL(path, import.meta.url).href;
  const module = (await import(/* @vite-ignore */ url)) as { default: Loaded };
  return portsOf(module.default);
}

const saved = process.env.OSPREY_LANE;
afterEach(() => {
  if (saved === undefined) delete process.env.OSPREY_LANE;
  else process.env.OSPREY_LANE = saved;
});

describe("each lane's local Playwright runs use ports of their own", () => {
  it.each(CONFIGS)("%s: two lanes never share a port", async (path) => {
    const admin = await load(path, "admin");
    const kase = await load(path, "case");
    expect(admin.length).toBeGreaterThan(0);
    expect(
      admin.filter((port) => kase.includes(port)),
      `admin ${admin}, case ${kase}`,
    ).toEqual([]);
  });

  it.each(CONFIGS)("%s: main keeps today's ports", async (path) => {
    const main = await load(path, "main");
    expect(
      main.every(
        (port) =>
          (port >= 5183 && port <= 5194) || (port >= 7217 && port <= 7220),
      ),
    ).toBe(true);
  });

  it("a lane not in the table is refused in words naming it", async () => {
    await expect(load(CONFIGS[0], "no-such-lane")).rejects.toThrow(
      /lane_ports\.tsv/,
    );
  });
});

describe("the table's blocks stay clear of each other and of every port already spoken for", () => {
  it("no lane's ports meet another lane's, a stack's, the owner's deployment's or the demo's", async () => {
    const table = parseTable(readFileSync(TABLE, "utf8"));
    const today = new Set<number>();
    for (const path of CONFIGS)
      for (const port of await load(path, "main")) today.add(port);
    const stacks = readFileSync(join(TABLE, "..", "lane_stacks.tsv"), "utf8")
      .split("\n")
      .filter((line) => line && !line.startsWith("#"))
      .map((line) => Number(line.split("\t")[3]));
    const spoken = new Set([...stacks, 2480, 5432, 80, 8000, 8080, 8081, 5173]);
    const owner = new Map<number, string>();
    for (const [lane, slot] of [["main", 0] as const, ...table]) {
      for (const base of today) {
        const port = base + STEP * slot;
        expect(
          spoken.has(port),
          `${lane}'s ${port} is already spoken for`,
        ).toBe(false);
        expect(
          owner.get(port),
          `${lane}'s ${port} is also ${owner.get(port)}'s`,
        ).toBeUndefined();
        owner.set(port, lane);
      }
    }
    expect(new Set(table.values()).size, "two lanes share a slot").toBe(
      table.size,
    );
  });

  it("a lane is $OSPREY_LANE, else its branch; a sub-branch takes its lane's slot", () => {
    const table = new Map([
      ["admin", 1],
      ["case", 2],
      ["case-b", 3],
    ]);
    expect(laneOf({}, "lane/case-b")).toBe("case-b");
    expect(laneOf({ OSPREY_LANE: "case" }, "lane/admin")).toBe("case");
    expect(laneOf({}, "main")).toBeNull();
    expect(laneOf({ OSPREY_LANE: "main" }, "lane/admin")).toBeNull();
    expect(slotOf("admin-ddl", table)).toBe(1);
    expect(slotOf("case-b-l37", table)).toBe(3);
    expect(slotOf(null, table)).toBe(0);
    expect(slotOf("admin", null)).toBe(0); // a checkout of the product alone: today's ports
    expect(() => slotOf("glass", table)).toThrow(/lane_ports\.tsv.*add "glass/);
  });
});
