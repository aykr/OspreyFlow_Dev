// @vitest-environment jsdom
// The workspace shell (ADR-097 step 1, design review items 1 and 16, Amendment 1).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClassificationStrip, highestMarking, screenMarking } from "./ClassificationStrip";
import { LeftRail } from "./LeftRail";

afterEach(cleanup);

const ORDER = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET", "TOP SECRET"];

describe("the protective marking", () => {
  it("is the highest classification among what is in the view, in the scheme's order", () => {
    expect(highestMarking(["OFFICIAL", "SECRET", "OFFICIAL-SENSITIVE"], ORDER)).toBe("SECRET");
  });

  it("is the scheme's lowest for an empty view", () => {
    expect(highestMarking([], ORDER)).toBe("OFFICIAL");
  });

  it("names a marking the scheme does not know rather than hiding it", () => {
    expect(highestMarking(["OFFICIAL", "UNKNOWN MARK"], ORDER)).toBe("UNKNOWN MARK");
  });

  // ADR-115 decision 2: the deployment's marking is the floor; data above it raises the strip.
  it("is never below the deployment's marking, and rises with what is on screen", () => {
    expect(screenMarking([], ORDER, "OFFICIAL-SENSITIVE")).toBe("OFFICIAL-SENSITIVE");
    expect(screenMarking(["OFFICIAL"], ORDER, "OFFICIAL-SENSITIVE")).toBe("OFFICIAL-SENSITIVE");
    expect(screenMarking(["SECRET"], ORDER, "OFFICIAL-SENSITIVE")).toBe("SECRET");
    expect(screenMarking(["OFFICIAL"], ORDER, null)).toBe("OFFICIAL");
  });

  it("is shown in a strip of its own, neutral, labelled for assistive technology", () => {
    render(<ClassificationStrip marking="OFFICIAL-SENSITIVE" />);
    const strip = screen.getByRole("note", { name: "Protective marking" });
    expect(strip.textContent).toBe("OFFICIAL-SENSITIVE");
  });
});

describe("the left rail", () => {
  const items = () => [
    { id: "cases", label: "Cases", icon: "cases" as const, onSelect: vi.fn() },
    { id: "history", label: "History", icon: "history" as const, onSelect: vi.fn() },
    { id: "watches", label: "Watches", icon: "watches" as const, onSelect: vi.fn(), pressed: true },
  ];

  it("names every entry for assistive technology, even folded to icons", () => {
    render(<LeftRail items={items()} />);
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    expect(nav).toBeTruthy();
    for (const name of ["Cases", "History", "Watches"]) expect(screen.getByRole("button", { name })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Watches" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("an entry does what it names", () => {
    const list = items();
    render(<LeftRail items={list} />);
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(list[1]!.onSelect).toHaveBeenCalled();
  });

  it("expands to show the names, and folds again", () => {
    render(<LeftRail items={items()} />);
    const toggle = screen.getByRole("button", { name: "Show names" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide names" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("History")).toBeTruthy();
  });
});

// ADR-115 E6 (the reference's rail): an entry may carry a count, said in its name and drawn as a badge
// in mono; a Help button at the foot reopens the workspace's welcome panel.
describe("the left rail's badge and Help", () => {
  it("draws a count on an entry and says it in the entry's name", () => {
    render(<LeftRail items={[{ id: "alerts", label: "Alerts", icon: "alerts", onSelect: () => undefined, badge: 3 }]} />);
    const alerts = screen.getByRole("button", { name: "Alerts, 3 open" });
    expect(alerts.querySelector(".left-rail__badge")?.textContent).toBe("3");
  });

  it("draws no badge for nothing open", () => {
    render(<LeftRail items={[{ id: "alerts", label: "Alerts", icon: "alerts", onSelect: () => undefined, badge: 0 }]} />);
    expect(screen.getByRole("button", { name: "Alerts" }).querySelector(".left-rail__badge")).toBeNull();
  });

  it("offers Help at the foot, which calls back", () => {
    const help = vi.fn();
    render(<LeftRail items={[]} onHelp={help} />);
    fireEvent.click(screen.getByRole("button", { name: "Help" }));
    expect(help).toHaveBeenCalled();
  });
});
