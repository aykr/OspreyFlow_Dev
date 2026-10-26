// @vitest-environment jsdom
// ADR-128 decision 3: opening an attachment of the case brief takes the person to where that thing
// lives. A canvas view is a case (a tab), a trend is on the Reports view's Trends tab, a saved
// pattern is in the Query builder panel and an assessment in the Inspector panel (both beside the
// canvas, which is where an analyst works with them).
import { afterEach, describe, expect, it, vi } from "vitest";

import { placeOf, revealPanel } from "./openAttachment";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("placeOf", () => {
  it("sends each kind to its own place", () => {
    expect(placeOf("view", "c2")).toEqual({ place: "case", id: "c2" });
    expect(placeOf("trend", "t1")).toEqual({ place: "reports", tab: "trends" });
    expect(placeOf("pattern", "p1")).toEqual({ place: "panel", panel: "query-builder" });
    expect(placeOf("assessment", "j1")).toEqual({ place: "panel", panel: "inspector" });
  });
});

function slot(id: string, expanded: boolean) {
  document.body.innerHTML = `
    <div data-panel-slot="${id}">
      <div class="side-panel-header"><button class="side-panel-header__toggle" aria-expanded="${expanded}">Name</button></div>
    </div>`;
  const toggle = document.querySelector<HTMLButtonElement>(".side-panel-header__toggle")!;
  const onClick = vi.fn(() => toggle.setAttribute("aria-expanded", String(toggle.getAttribute("aria-expanded") !== "true")));
  toggle.addEventListener("click", onClick);
  return { toggle, onClick };
}

describe("revealPanel", () => {
  it("unfolds a folded panel and puts focus on its header", () => {
    const { toggle, onClick } = slot("query-builder", false);
    expect(revealPanel("query-builder")).toBe(true);
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(toggle);
  });

  it("leaves an open panel open, and only focuses it", () => {
    const { toggle, onClick } = slot("inspector", true);
    expect(revealPanel("inspector")).toBe(true);
    expect(onClick).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(toggle);
  });

  it("says so when the panel is not on the page, and touches nothing", () => {
    document.body.innerHTML = `<button id="other">x</button>`;
    expect(revealPanel("query-builder")).toBe(false);
  });
});
