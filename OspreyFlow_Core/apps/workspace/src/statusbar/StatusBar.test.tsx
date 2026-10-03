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
