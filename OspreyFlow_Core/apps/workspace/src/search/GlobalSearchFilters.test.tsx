// @vitest-environment jsdom
//
// The Filters button under the search box (ADR-061): ignore case, match mode, entity types, and
// searching only what is on screen. With every filter at its default the box behaves exactly as
// `GlobalSearch.test.tsx` already proves.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { GlobalSearch, SUGGEST_PAUSE_MS } from "./GlobalSearch";

function node(id: string, type: string, value: string): Node {
  return { id, type, properties: { value_normalised: value } } as unknown as Node;
}

function stubFetch(): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ nodes: [], more: false }) }));
  vi.stubGlobal("fetch", mock);
  return mock;
}

const bodyOf = (mock: ReturnType<typeof vi.fn>, call = 0) =>
  JSON.parse(String((mock.mock.calls[call] as [string, RequestInit])[1].body)) as Record<string, unknown>;

async function pause(ms = SUGGEST_PAUSE_MS): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function mount(extra: Partial<Parameters<typeof GlobalSearch>[0]> = {}): void {
  render(
    <GlobalSearch investigationId="inv-1"
      apiBaseUrl="http://api"
      bearerToken="t"
      onSelect={vi.fn()}
      entityTypes={["Endpoint", "Person"]}
      {...extra}
    />,
  );
}

function type(text: string): HTMLElement {
  const box = screen.getByRole("combobox");
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: text } });
  return box;
}

const openFilters = () => fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the Filters button", () => {
  it("is there, with the panel closed until it is pressed", () => {
    stubFetch();
    mount();
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "Ignore case" })).toBeNull();
    openFilters();
    expect(screen.getByRole("checkbox", { name: "Ignore case" })).toBeTruthy();
  });

  it("says how many filters are on", () => {
    stubFetch();
    mount();
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    fireEvent.click(screen.getByRole("radio", { name: "Contains" }));
    expect(screen.getByRole("button", { name: "Filters (2)" })).toBeTruthy();
  });
});

describe("asking the Conduit with filters on", () => {
  it("sends ignore case, the match mode and the chosen types", async () => {
    const mock = stubFetch();
    mount();
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    fireEvent.click(screen.getByRole("radio", { name: "Contains" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    type("jef");
    await pause();
    expect(bodyOf(mock)).toEqual({
      query: "jef",
      limit: 10,
      ignore_case: true,
      mode: "contains",
      types: ["Person"],
    });
  });

  it("asks again, with the new filter, when a filter changes after the text is typed", async () => {
    const mock = stubFetch();
    mount();
    type("jef");
    await pause();
    expect(mock).toHaveBeenCalledTimes(1);
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    await pause();
    expect(mock).toHaveBeenCalledTimes(2);
    expect(bodyOf(mock, 1).ignore_case).toBe(true);
  });

  it("does not ask the Conduit again for a stale question after reset", async () => {
    const mock = stubFetch();
    mount();
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    type("jef");
    await pause();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(bodyOf(mock)).toEqual({ query: "jef", limit: 10 });
  });
});

describe("searching only what is on screen", () => {
  const onScreen = [node("1", "Endpoint", "jeff@enron.com"), node("2", "Person", "Jeffrey Archer")];

  it("asks the Conduit nothing and answers from the nodes drawn", async () => {
    const mock = stubFetch();
    mount({ screenNodes: () => onScreen });
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: /Only nodes on screen/ }));
    type("jef");
    await pause();
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByText("Endpoint: jeff@enron.com")).toBeTruthy();
    expect(screen.queryByText("Person: Jeffrey Archer")).toBeNull();
  });

  it("says plainly when nothing on screen matches", async () => {
    stubFetch();
    mount({ screenNodes: () => onScreen });
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: /Only nodes on screen/ }));
    type("zzz");
    await pause();
    expect(screen.getByRole("status").textContent).toMatch(/on screen/i);
  });

  it("honours ignore case and type filters on the screen search too", async () => {
    stubFetch();
    mount({ screenNodes: () => onScreen });
    openFilters();
    fireEvent.click(screen.getByRole("checkbox", { name: /Only nodes on screen/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Ignore case" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    type("JEF");
    await pause();
    expect(screen.getByText("Person: Jeffrey Archer")).toBeTruthy();
    expect(screen.queryByText("Endpoint: jeff@enron.com")).toBeNull();
  });
});
