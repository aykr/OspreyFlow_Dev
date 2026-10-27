// DESIGN.md v0.3 §5a (ADR-115 decision 9): each region of the workspace takes its size from the
// layout tokens, never a number of its own — so a size the contract changes is changed once.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

function rule(selector: string): Record<string, string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(CSS);
  if (!match) throw new Error(`no rule for ${selector}`);
  return Object.fromEntries(
    match[1]!.split(";").map((d) => d.split(":").map((x) => x.trim())).filter(([k, v]) => k && v) as [string, string][],
  );
}

describe("the workspace's regions", () => {
  it("take their sizes from §5a's tokens", () => {
    expect(rule(".top-bar").height).toBe("var(--h-top-bar)");
    expect(rule(".left-rail").width).toBe("var(--w-rail)");
    expect(rule(".left-rail__item").height).toBe("var(--h-rail-button)");
    expect(rule(".left-rail__item")["min-width"]).toBe("var(--h-rail-button)");
    expect(rule(".view-toolbar").height).toBe("var(--h-canvas-toolbar)");
    expect(rule(".canvas-toolbar")["min-height"]).toBe("var(--h-canvas-toolbar)");
    expect(rule(".status-bar")["min-height"]).toBe("var(--h-status-bar)");
    expect(rule(".bottom-panel__head").height).toBe("var(--h-timeline)");
  });

  it("set the status bar's counts in mono 11px with 16px between them", () => {
    const bar = rule(".status-bar");
    expect(bar.gap).toBe("var(--sp-4) var(--sp-16)");
    expect(bar["font-size"]).toBe("var(--fs-11)");
  });

  it("offsets the search box's Add many button by the spacing token, not a literal 32px", () => {
    expect(rule(".global-search__add").right).toBe("calc(var(--sp-4) + var(--sp-32))");
  });
});
