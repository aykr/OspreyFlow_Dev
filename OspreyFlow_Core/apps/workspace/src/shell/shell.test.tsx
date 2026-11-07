// @vitest-environment jsdom
// The workspace shell (ADR-097 step 1, design review items 1 and 16, Amendment 1).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClassificationStrip, highestMarking, screenMarking } from "./ClassificationStrip";
import { LeftRail } from "./LeftRail";
import { TopBar } from "./TopBar";

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
    { id: "alerts", label: "Monitoring", icon: "alerts" as const, onSelect: vi.fn(), pressed: true },
  ];

  it("names every entry for assistive technology, even folded to icons", () => {
    render(<LeftRail items={items()} />);
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    expect(nav).toBeTruthy();
    for (const name of ["Cases", "History", "Monitoring"]) expect(screen.getByRole("button", { name })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Monitoring" }).getAttribute("aria-pressed")).toBe("true");
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

// ADR-145 Amendment 2 (variant B): the rail's ⋯ More, and the top bar's More views.
describe("the rail's More and the top bar's More views", () => {
  it("lists the rail's other destinations under ⋯ More, chosen from it and closed by the choice", () => {
    const chose = vi.fn();
    render(
      <LeftRail
        items={[{ id: "cases", label: "Cases", icon: "cases", onSelect: () => undefined }]}
        more={[
          { id: "ownership", label: "Ownership", icon: "ownership", onSelect: () => chose("ownership") },
          { id: "history", label: "History", icon: "history", onSelect: () => chose("history"), pressed: true },
        ]}
      />,
    );
    const more = screen.getByRole("button", { name: "More, History open" });
    expect(more.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(more);
    const menu = within(screen.getByRole("group", { name: "More" }));
    expect(menu.getAllByRole("button").map((b) => b.textContent)).toEqual(["Ownership", "History"]);
    fireEvent.click(menu.getByRole("button", { name: "Ownership" }));
    expect(chose).toHaveBeenCalledWith("ownership");
    expect(screen.queryByRole("group", { name: "More" })).toBeNull();
  });

  it("draws no More for a rail with nothing beyond it", () => {
    render(<LeftRail items={[{ id: "cases", label: "Cases", icon: "cases", onSelect: () => undefined }]} />);
    expect(screen.queryByRole("button", { name: /^More/ })).toBeNull();
  });

  it("puts the views used less under More views, naming the one open", () => {
    const chose = vi.fn();
    const view = (id: string, pressed = false) => ({ id, label: id[0]!.toUpperCase() + id.slice(1), pressed, onSelect: () => chose(id) });
    const { rerender } = render(
      <TopBar app="glass" views={[view("graph", true), view("map")]} moreViews={[view("matrix"), view("reports")]} account={null} />,
    );
    expect(within(screen.getByRole("group", { name: "View" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Graph", "Map"]);
    fireEvent.click(screen.getByRole("button", { name: /^More views/ }));
    fireEvent.click(within(screen.getByRole("group", { name: "More views" })).getByRole("button", { name: "Reports" }));
    expect(chose).toHaveBeenCalledWith("reports");
    rerender(<TopBar app="glass" views={[view("graph"), view("map")]} moreViews={[view("matrix"), view("reports", true)]} account={null} />);
    expect(screen.getByRole("button", { name: /^Reports/ }).className).toContain("menu-button--pressed");
  });
});
