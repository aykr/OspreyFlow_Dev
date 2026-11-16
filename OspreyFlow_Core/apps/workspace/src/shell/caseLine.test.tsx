// @vitest-environment jsdom
// ADR-145 Amendment 19 (v0.6.1, the Glass's rows): the case line in the Glass. Its slim form, for a toolbar hidden
// (decision 6), keeps the case, *Saved views (n)* and what is open, drops "You are in the Glass" from sight (the region
// is still named by it) and "reads …", and draws the place's `end` (*Show toolbar*) last on the line.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("starts with the case, no separator before it, while You are in is out of sight", () => {
    applyBrand(brand);
    render(line({ slim: true }));
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    const row = region.querySelector(".govuk-notification-banner__content") ?? region;
    const drawn = [...row.children].filter((c) => !c.classList.contains("visually-hidden"));
    expect(drawn[0]!.textContent).toBe("Case");
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

// ADR-145 Amendment 19 decisions 1–3: what is open is said on the case line; the strip under it is gone.
const NOTE = {
  element_id: "e1", kind: "node" as const, label: "Mercer", marking: "OFFICIAL", grading: "B21",
  source_note: "Wing officer report, 4 Nov", words: "Drawn by A. Field, merged as load promotion-9", merged: true,
};  // prettier-ignore

describe.each(["ospreyflow", "govuk"] as const)("the case line's state (%s)", (brand) => {
  it("ends Whole case with no saved view open, and names no saved view", () => {
    applyBrand(brand);
    render(line({ caseState: "whole" }));
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(within(region).getByText("Whole case")).toBeTruthy();
    expect(region.textContent).not.toContain("Saved view:");
    expect(within(region).queryByRole("button", { name: "Back to the whole case" })).toBeNull();
  });

  it("names the open saved view with its tag, offers Details and Back to the whole case, and takes focus to its name", () => {
    applyBrand(brand);
    let back = 0;
    render(line({ caseState: { id: "v1", name: "Vance network", shared: true, missing: 2, onBack: () => (back += 1) } }));
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    const named = within(region).getByText(/^Saved view:/);
    expect(named.textContent).toBe("Saved view: Vance network");
    expect(document.activeElement).toBe(named);
    expect(within(region).getByText("Shared")).toBeTruthy();
    expect(region.textContent).not.toContain("Whole case");
    const details = within(region).getByRole("button", { name: "Details" });
    expect(details.getAttribute("aria-expanded")).toBe("false");
    expect(details.getAttribute("aria-controls")).toBe("saved-view-details");
    const way = within(region).getByRole("button", { name: "Back to the whole case" });
    expect(way.className).toContain(brand === "govuk" ? "govuk-back-link" : "context-banner__whole");
    // The way back is after Details, and "reads …" after it.
    expect(details.compareDocumentPosition(way) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(region.textContent!.indexOf("Back to the whole case")).toBeLessThan(region.textContent!.indexOf("reads Prison intel"));
    fireEvent.click(way);
    expect(back).toBe(1);
  });

  it("Details opens over the canvas with the count, the case untouched, the way it came and the drawing's notes; Esc closes it to Details", () => {
    applyBrand(brand);
    let alert = 0;
    render(line({
      caseState: { id: "v1", name: "Night visits", shared: false, missing: 2, onBack: () => undefined, annotations: [NOTE],
        from: { label: "From alert A14", backLabel: "← Back to the alert", onBack: () => (alert += 1) } },
    }));  // prettier-ignore
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(within(region).getByText("Private")).toBeTruthy();
    // The way back to the alert stays on the line itself.
    fireEvent.click(within(region).getByRole("button", { name: "← Back to the alert" }));
    expect(alert).toBe(1);
    expect(screen.queryByRole("region", { name: "Saved view details" })).toBeNull();
    const details = within(region).getByRole("button", { name: "Details" });
    fireEvent.click(details);
    expect(details.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByRole("region", { name: "Saved view details" });
    expect(panel.id).toBe("saved-view-details");
    expect(panel.textContent).toContain("2 items in this view could not be shown");
    expect(panel.textContent).toContain("Nothing in a saved view changes the case.");
    expect(panel.textContent).toContain("From alert A14");
    fireEvent.click(within(panel).getByRole("button", { name: "← Back to the alert" }));
    expect(alert).toBe(2);
    const notes = within(panel).getByRole("button", { name: "Notes from the drawing (1)" });
    expect(screen.queryByText("Mercer")).toBeNull();
    fireEvent.click(notes);
    expect(within(panel).getByText("Mercer")).toBeTruthy();
    expect(within(panel).getByText("Drawn by A. Field, merged as load promotion-9.")).toBeTruthy();
    fireEvent.keyDown(notes, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Saved view details" })).toBeNull();
    expect(details.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(details);
  });

  it("offers no notes on a view that has none, and no count when nothing was left out", () => {
    applyBrand(brand);
    render(line({ caseState: { id: "v2", name: "Wing B", shared: true, missing: 0, onBack: () => undefined } }));
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    const panel = screen.getByRole("region", { name: "Saved view details" });
    expect(within(panel).queryByRole("button", { name: /Notes from the drawing/ })).toBeNull();
    expect(panel.textContent).not.toContain("could not be shown");
  });

  it("keeps the state on the slim line, Back to the whole case with it", () => {
    applyBrand(brand);
    render(line({ slim: true, caseState: { id: "v1", name: "Vance network", shared: true, missing: 0, onBack: () => undefined } }));
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(within(region).getByText(/^Saved view:/).textContent).toBe("Saved view: Vance network");
    expect(within(region).getByRole("button", { name: "Back to the whole case" })).toBeTruthy();
  });
});
