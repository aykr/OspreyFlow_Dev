// @vitest-environment jsdom
// The search box offers "Add many from a list" (ADR-128 decision 1, B2) when the page can draw what is
// added, and only then: a box with no one to draw for it (the From and To boxes of Find connections)
// offers nothing new.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalSearch } from "./GlobalSearch";

afterEach(cleanup);

function mount(onApplyDelta?: () => void) {
  render(
    <GlobalSearch
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="inv-1"
      onSelect={vi.fn()}
      onApplyDelta={onApplyDelta}
    />,
  );
}

describe("the search box's add-many button", () => {
  it("is not there when the page cannot draw what is added", () => {
    mount();
    expect(screen.queryByRole("button", { name: "Add many from a list" })).toBeNull();
  });

  it("opens the paste box and the file choice, and closes them again", () => {
    mount(vi.fn());
    const opener = screen.getByRole("button", { name: "Add many from a list" });
    expect(opener.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: "Add many from a list" })).toBeNull();
    fireEvent.click(opener);
    expect(opener.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("group", { name: "Add many from a list" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: /identifiers/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group", { name: "Add many from a list" })).toBeNull();
    expect(opener.getAttribute("aria-expanded")).toBe("false");
  });
});
