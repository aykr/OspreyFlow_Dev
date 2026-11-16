// @vitest-environment jsdom
// ADR-145 Amendment 19 (v0.6.1, the Glass's rows): the case line in the Glass. Its slim form, for a toolbar hidden
// (decision 6), keeps the case, *Saved views (n)* and what is open, drops "You are in the Glass" from sight (the region
// is still named by it) and "reads …", and draws the place's `end` (*Show toolbar*) last on the line.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand } from "../brand/brand";
import { ContextBanner } from "./ContextBanner";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

const line = (extra: Partial<Parameters<typeof ContextBanner>[0]> = {}) => (
  <ContextBanner
    place="glass"
    caseSwitcher={<button type="button">Case: Kestrel</button>}
    datasets={["Prison intel"]}
    onViews={() => undefined}
    savedViews={7}
    crossLink={{ label: "Open this case's data in the Ingest Studio ↗", shortLabel: "Open in the Ingest Studio ↗", onFollow: () => undefined }}
    {...extra}
  />
);

describe.each(["ospreyflow", "govuk"] as const)("the case line's slim form (%s)", (brand) => {
  it("keeps the case and Saved views, names the region as before, and drops You are in and reads from sight", () => {
    applyBrand(brand);
    render(line({ slim: true }));
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(within(region).getByRole("button", { name: "Case: Kestrel" })).toBeTruthy();
    expect(within(region).getByRole("button", { name: "Saved views (7)" })).toBeTruthy();
    expect(region.textContent).not.toContain("reads Prison intel");
    // The heading stays for a screen reader, out of sight.
    expect(within(region).getByRole("heading", { name: "You are in the Glass" }).className).toContain("visually-hidden");
    // The cross-link is an action of the line, kept in its short words (no action is lost to a hidden toolbar).
    expect(within(region).getByRole("button", { name: "Open in the Ingest Studio ↗" })).toBeTruthy();
  });

  it("draws the end slot last on the line, in both forms", () => {
    applyBrand(brand);
    for (const slim of [false, true]) {
      render(line({ slim, end: <button type="button">Show toolbar</button> }));
      const region = screen.getByRole("region", { name: "You are in the Glass" });
      const buttons = within(region).getAllByRole("button");
      expect(buttons.at(-1)!.textContent).toBe("Show toolbar");
      cleanup();
    }
  });

  it("is the full line without slim: You are in in sight and reads drawn", () => {
    applyBrand(brand);
    render(line());
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(region.textContent).toContain("reads Prison intel");
    expect(within(region).getByRole("heading", { name: "You are in the Glass" }).className).not.toContain("visually-hidden");
  });
});
