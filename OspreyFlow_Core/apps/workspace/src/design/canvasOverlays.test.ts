// ADR-115 E4 (review item 10; the reference's canvas): the legend at the top right of the canvas with
// the zoom group under it, both in one column clear of the canvas toolbar.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const body = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(CSS)?.[1] ?? "";
  return Object.fromEntries(body.split(";").map((d) => d.split(":").map((x) => x.trim())).filter(([k, v]) => k && v));
};

describe("the canvas's corner overlays", () => {
  it("stack the legend over the zoom group at the top right, below the toolbar", () => {
    const corner = rule(".canvas-corner");
    expect(corner.position).toBe("absolute");
    expect(corner.right).toBe("var(--sp-8)");
    // Below the toolbar as it is drawn, not as one row: it wraps on a narrow canvas, and the legend
    // then covered its second row (the owner, 14 October 2026). The canvas measures it.
    expect(corner.top).toBe("calc(var(--canvas-toolbar-height, var(--h-canvas-toolbar)) + var(--sp-8))");
    expect(corner["flex-direction"]).toBe("column");
    expect(rule(".canvas-legend").position).toBeUndefined();
    expect(rule(".canvas-zoom").position).toBeUndefined();
  });

  // The owner, 14 October 2026 ("more elegant and intuitive"), after the reference's bar: one line,
  // each action's words on it — "Show links among these" had wrapped to four lines.
  it("keep the selection bar on one line, its actions quiet, Clear after a hairline", () => {
    expect(rule(".selection-bar")["white-space"]).toBe("nowrap");
    expect(rule(".selection-bar .btn--quiet")["border-color"]).toBe("transparent");
    expect(rule(".selection-bar__divider").width).toBe("1px");
  });
});
