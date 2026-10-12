// @vitest-environment jsdom
//
// The status bar never lies (spec 02 §2): a folded group hides its members from the drawing, so the
// bar says how many nodes are folded rather than leaving the analyst to think the picture is whole.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusBar } from "./StatusBar";

afterEach(cleanup);

describe("StatusBar", () => {
  it("says nothing about groups when nothing is folded", () => {
    render(<StatusBar nodeCount={10} edgeCount={12} dimmedCount={0} filteredCount={0} />);
    expect(screen.getByRole("status").textContent).not.toContain("folded");
  });

  it("says how many nodes are folded into groups", () => {
    render(
      <StatusBar nodeCount={10} edgeCount={12} dimmedCount={0} filteredCount={0} groupedCount={1234} />,
    );
    expect(screen.getByRole("status").textContent).toContain("1,234 folded into groups");
  });
});

// ADR-097 step 3: each count is a pair, its number a literal value in mono and its words in the UI
// face; the bar itself is not set in mono. ADR-115 (DESIGN.md v0.3, the reference's status bar): the
// pairs stand apart by 16px, with no separator character between them.
describe("StatusBar pairs", () => {
  it("draws each count as a number in mono beside its words, apart and with no separator", () => {
    render(<StatusBar nodeCount={12481} edgeCount={38902} dimmedCount={214} filteredCount={6} />);
    const bar = screen.getByRole("status");
    expect(bar.classList.contains("value")).toBe(false);
    const pairs = Array.from(bar.querySelectorAll(".status-pair"));
    expect(pairs.map((p) => [p.querySelector(".value")?.textContent, p.textContent])).toEqual([
      ["12,481", "12,481 nodes"],
      ["38,902", "38,902 edges"],
      ["214", "214 dimmed by filter"],
      ["6", "6 hidden by handling"],
    ]);
    expect(bar.querySelectorAll(".status-pair__sep")).toHaveLength(0);
    expect(bar.textContent).not.toContain("·");
  });
});

// ADR-115 E4 (the reference's status bar): a tip at the right, outside the counts' live region so a
// new tip is not read out as a change to the counts; *Next tip* steps through them.
describe("StatusBar tip", () => {
  it("shows a tip with a way to the next one, outside the live counts", () => {
    render(<StatusBar nodeCount={1} edgeCount={0} dimmedCount={0} filteredCount={0} />);
    const tip = screen.getByRole("region", { name: "Tip" });
    expect(screen.getByRole("status").contains(tip)).toBe(false);
    const first = tip.textContent;
    expect(first).toContain("Press / to search entities, identifiers and documents.");
    fireEvent.click(screen.getByRole("button", { name: "Next tip" }));
    expect(tip.textContent).not.toBe(first);
    expect(tip.textContent).toContain("press Enter to expand it by one hop");
  });
});
