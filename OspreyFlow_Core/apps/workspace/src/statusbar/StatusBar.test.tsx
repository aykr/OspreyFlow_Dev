// @vitest-environment jsdom
//
// The status bar never lies (spec 02 §2): a folded group hides its members from the drawing, so the
// bar says how many nodes are folded rather than leaving the analyst to think the picture is whole.
import { cleanup, render, screen } from "@testing-library/react";
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
// face, with a quiet separator between pairs; the bar itself is not set in mono.
describe("StatusBar pairs", () => {
  it("draws each count as a number in mono beside its words, separated", () => {
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
    expect(bar.querySelectorAll(".status-pair__sep")).toHaveLength(3);
  });
});
