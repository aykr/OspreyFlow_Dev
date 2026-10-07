// @vitest-environment jsdom
//
// Where the Filters button sits (ADR-065): inside the search box's own field, not under it, so the
// top bar stays one line. The behaviour of the filters is in `GlobalSearchFilters.test.tsx`.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalSearch } from "./GlobalSearch";

afterEach(cleanup);

describe("the search box", () => {
  it("holds the Filters button in the same field as the text box", () => {
    render(<GlobalSearch investigationId="inv-1" apiBaseUrl="http://api" bearerToken="t" onSelect={vi.fn()} entityTypes={["Person"]} />);
    const field = screen.getByRole("combobox").closest(".global-search__field");
    expect(field).not.toBeNull();
    expect(field!.contains(screen.getByRole("button", { name: "Filters" }))).toBe(true);
  });
});

describe("the Filters button, as an icon (owner, 3 October 2026: a text button inside the box 'looks strange')", () => {
  it("is an icon with the name Filters, and no visible word", () => {
    render(<GlobalSearch investigationId="inv-1" apiBaseUrl="http://api" bearerToken="t" onSelect={vi.fn()} entityTypes={["Person"]} />);
    const button = screen.getByRole("button", { name: "Filters" });
    expect(button.querySelector("svg")).not.toBeNull();
    expect((button.textContent ?? "").trim()).toBe("");
    expect(button.getAttribute("title")).toBe("Filters");
  });

  it("shows how many filters are on as a small count, and says so in its name", () => {
    render(<GlobalSearch investigationId="inv-1" apiBaseUrl="http://api" bearerToken="t" onSelect={vi.fn()} entityTypes={["Person"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /ignore case/i }));
    const button = screen.getByRole("button", { name: /^Filters \(/ });
    expect(button.textContent?.trim()).toMatch(/^\d+$/);
    expect(button.getAttribute("aria-label")).toBe(`Filters (${button.textContent!.trim()})`);
  });
});
