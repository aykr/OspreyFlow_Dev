// @vitest-environment jsdom
// ADR-143 Amendment 2 decision 7 (L3.9): a merged drawing's view offers its notes. What would fail if
// it were wrong: the notes offered on a view that has none; a note shown before it is asked for, or
// not shown when it is; the toggle not saying whether it is open.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ViewLensBanner } from "./ViewLensBanner";

afterEach(cleanup);

const NOTE = {
  element_id: "e1", kind: "node" as const, label: "Mercer", marking: "OFFICIAL", grading: "B21",
  source_note: "Wing officer report, 4 Nov", words: "Drawn by A. Field, merged as load promotion-9", merged: true,
};  // prettier-ignore

describe("the view's notes from the drawing", () => {
  it("are not offered on a view that has none", () => {
    render(<ViewLensBanner name="Wing B" shared={false} missing={0} onBack={() => {}} />);
    expect(screen.queryByRole("button", { name: /Notes from the drawing/ })).toBeNull();
  });

  it("open and close, each with what was drawn and how it was merged", () => {
    render(<ViewLensBanner name="Night visits" shared missing={0} onBack={() => {}} annotations={[NOTE]} />);
    const toggle = screen.getByRole("button", { name: "Notes from the drawing (1)" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Mercer")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Mercer")).toBeTruthy();
    expect(screen.getByText("OFFICIAL · graded B21 · Wing officer report, 4 Nov")).toBeTruthy();
    expect(screen.getByText("Drawn by A. Field, merged as load promotion-9.")).toBeTruthy();
    fireEvent.click(toggle);
    expect(screen.queryByText("Mercer")).toBeNull();
  });
});
