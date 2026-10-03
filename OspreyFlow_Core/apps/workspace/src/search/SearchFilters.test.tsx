// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchFilters } from "./SearchFilters";
import { DEFAULT_SEARCH_OPTIONS, type SearchOptions } from "./searchOptions";

afterEach(cleanup);

function setup(options: Partial<SearchOptions> = {}, entityTypes = ["Endpoint", "Person", "Account"]) {
  const onChange = vi.fn();
  render(
    <SearchFilters
      options={{ ...DEFAULT_SEARCH_OPTIONS, ...options }}
      entityTypes={entityTypes}
      onChange={onChange}
    />,
  );
  return onChange;
}

describe("SearchFilters", () => {
  it("offers an ignore-case tick box and reports the change", () => {
    const onChange = setup();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_OPTIONS, ignoreCase: true });
  });

  it("shows ignore case as ticked when it is on", () => {
    setup({ ignoreCase: true });
    expect((screen.getByRole("checkbox", { name: "Ignore case" }) as HTMLInputElement).checked).toBe(true);
  });

  it("offers the three match modes, with the current one chosen", () => {
    setup({ mode: "contains" });
    expect((screen.getByRole("radio", { name: "Contains" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("radio", { name: "Starts with" }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByRole("radio", { name: "Exact" })).toBeTruthy();
  });

  it("reports a change of match mode", () => {
    const onChange = setup();
    fireEvent.click(screen.getByRole("radio", { name: "Exact" }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_OPTIONS, mode: "exact" });
  });

  it("lists the entity types it is given, none ticked meaning all", () => {
    setup();
    for (const name of ["Endpoint", "Person", "Account"]) {
      expect((screen.getByRole("checkbox", { name }) as HTMLInputElement).checked).toBe(false);
    }
    expect(screen.getByText(/none ticked searches every type/i)).toBeTruthy();
  });

  it("adds and removes a type from the chosen list", () => {
    const onChange = setup({ types: ["Person"] });
    fireEvent.click(screen.getByRole("checkbox", { name: "Endpoint" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_SEARCH_OPTIONS, types: ["Person", "Endpoint"] });
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_SEARCH_OPTIONS, types: [] });
  });

  it("offers a graph-on-screen-only tick box", () => {
    const onChange = setup();
    fireEvent.click(screen.getByRole("checkbox", { name: /Only nodes on screen/ }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_OPTIONS, onScreenOnly: true });
  });

  it("resets every filter in one step", () => {
    const onChange = setup({ ignoreCase: true, mode: "exact", types: ["Person"], onScreenOnly: true });
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(onChange).toHaveBeenCalledWith(DEFAULT_SEARCH_OPTIONS);
  });
});
