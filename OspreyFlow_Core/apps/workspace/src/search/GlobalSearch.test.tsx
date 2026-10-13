// @vitest-environment jsdom
//
// The search box as the analyst types (ADR-059). Seen, 2 October 2026: typing `C` or part of an
// account id found nothing, because the box asked for an exact match. It now asks `/v1/investigations/inv-1/suggest`
// from the third character, after a pause, ignores an answer to a question already superseded,
// says when more matched than are shown, and says when the Conduit could not answer.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { GlobalSearch, SEARCH_HINT_MS, SUGGEST_MIN_CHARS, SUGGEST_PAUSE_MS } from "./GlobalSearch";

function account(id: string, value: string): Node {
  return { id, type: "Endpoint", properties: { value_normalised: value } } as unknown as Node;
}

type Reply = { status?: number; body?: unknown; delayMs?: number };

function stubFetch(reply: (query: string) => Reply): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    if (!url.endsWith("/v1/investigations/inv-1/suggest") || init?.method !== "POST") throw new Error(`unexpected request ${url}`);
    const { query } = JSON.parse(String(init.body)) as { query: string };
    const { status = 200, body = { nodes: [], more: false }, delayMs = 0 } = reply(query);
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return { ok: status < 300, status, json: async () => body };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function type(text: string): HTMLElement {
  const box = screen.getByRole("combobox");
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: text } });
  return box;
}

async function pause(ms = SUGGEST_PAUSE_MS): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function mount(onSelect = vi.fn()): ReturnType<typeof vi.fn> {
  render(<GlobalSearch investigationId="inv-1" apiBaseUrl="http://api" bearerToken="t" onSelect={onSelect} />);
  return onSelect;
}

describe("GlobalSearch as the analyst types", () => {
  it("asks nothing until two characters are typed, and says so rather than staying silent", async () => {
    const mock = stubFetch(() => ({}));
    mount();
    type("C");
    await pause(SUGGEST_PAUSE_MS * 4);
    expect(SUGGEST_MIN_CHARS).toBe(2);
    expect(mock).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toBe("Type at least 2 characters to search.");
  });

  it("asks after two characters, and stops saying to type more", async () => {
    const mock = stubFetch(() => ({ body: { nodes: [account("n1", "QQ118439C")], more: false } }));
    mount();
    type("QQ");
    await pause(SUGGEST_PAUSE_MS);
    expect(mock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Type at least 2 characters to search.")).toBeNull();
  });

  it("asks once, after the pause, for what was typed, with a limit of ten", async () => {
    const mock = stubFetch(() => ({ body: { nodes: [account("n1", "C1305486145")], more: false } }));
    mount();
    type("C13");
    await pause(SUGGEST_PAUSE_MS - 1);
    expect(mock).not.toHaveBeenCalled();
    await pause(1);
    expect(mock).toHaveBeenCalledTimes(1);
    const [, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ query: "C13", limit: 10 });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t");
  });

  it("shows the value that matched, not the node's opaque id", async () => {
    stubFetch(() => ({ body: { nodes: [account("paysim-acct-29dfa1bd", "C1305486145")], more: false } }));
    mount();
    type("C13");
    await pause();
    expect(screen.getByText("Endpoint: C1305486145")).toBeTruthy();
    expect(document.body.textContent).not.toContain("paysim-acct-29dfa1bd");
  });

  it("sends one request for a burst of typing, for the final text", async () => {
    const mock = stubFetch(() => ({}));
    mount();
    const box = type("C13");
    await pause(100);
    fireEvent.change(box, { target: { value: "C130" } });
    await pause(100);
    fireEvent.change(box, { target: { value: "C1305" } });
    await pause();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String((mock.mock.calls[0] as [string, RequestInit])[1].body)).query).toBe("C1305");
  });

  it("ignores a slow answer to a question the analyst has already moved past", async () => {
    stubFetch((query) =>
      query === "C13"
        ? { delayMs: 2000, body: { nodes: [account("old", "C13-stale")], more: false } }
        : { body: { nodes: [account("new", "C1305-fresh")], more: false } },
    );
    mount();
    const box = type("C13");
    await pause();
    fireEvent.change(box, { target: { value: "C1305" } });
    await pause();
    await pause(3000);
    expect(screen.queryByText("Endpoint: C13-stale")).toBeNull();
    expect(screen.getByText("Endpoint: C1305-fresh")).toBeTruthy();
  });

  it("says when more matched than are shown, and not otherwise", async () => {
    stubFetch((query) => ({ body: { nodes: [account("n1", "C1305486145")], more: query === "C13" } }));
    mount();
    const box = type("C13");
    await pause();
    expect(screen.getByRole("status").textContent).toMatch(/more/i);
    fireEvent.change(box, { target: { value: "C130" } });
    await pause();
    expect(screen.queryByRole("status")).toBeNull();
  });

  // Seen 3 October 2026: "Showing the first 10; more match. Keep typing to narrow." sat in the page's
  // flow under the box, so the one-line top bar grew a second line the moment a list came back. It is
  // now a hint laid over the page (see topBarStyle.test.ts) that fades once it has been read. It stays
  // in the page for a screen reader, and comes back whenever a new answer says it again.
  it("fades the 'more match' hint after a few seconds, keeps it readable, and brings it back with a new answer", async () => {
    stubFetch(() => ({ body: { nodes: [account("n1", "C1305486145")], more: true } }));
    mount();
    const box = type("C13");
    await pause();
    const hint = screen.getByRole("status");
    expect(hint.getAttribute("data-faded")).toBeNull();
    await pause(SEARCH_HINT_MS + 50);
    expect(hint.getAttribute("data-faded")).toBe("true");
    expect(hint.textContent).toMatch(/more match/i);
    fireEvent.change(box, { target: { value: "C130" } });
    await pause();
    expect(screen.getByRole("status").getAttribute("data-faded")).toBeNull();
  });

  it("does not fade a message that says nothing matched or that the Conduit could not answer", async () => {
    stubFetch(() => ({ status: 500 }));
    mount();
    type("C13");
    await pause();
    await pause(SEARCH_HINT_MS + 50);
    expect(screen.getByRole("status").getAttribute("data-faded")).toBeNull();
  });

  it("says so when the Conduit cannot answer, and does not leave the last answer standing", async () => {
    stubFetch((query) =>
      query === "C13" ? { body: { nodes: [account("n1", "C1305486145")], more: false } } : { status: 500 },
    );
    mount();
    const box = type("C13");
    await pause();
    fireEvent.change(box, { target: { value: "C130" } });
    await pause();
    expect(screen.getByRole("status").textContent).toMatch(/unavailable/i);
    expect(screen.queryByText("Endpoint: C1305486145")).toBeNull();
  });

  it("says when nothing starts with what was typed", async () => {
    stubFetch(() => ({ body: { nodes: [], more: false } }));
    mount();
    type("ZZZ");
    await pause();
    expect(screen.getByRole("status").textContent).toMatch(/no match/i);
  });

  it("selects a suggestion with the keyboard and with the mouse", async () => {
    const node = account("n2", "C1420196421");
    stubFetch(() => ({ body: { nodes: [account("n1", "C1305486145"), node], more: false } }));
    const onSelect = mount();
    const box = type("C1");
    fireEvent.change(box, { target: { value: "C14" } });
    await pause();
    screen.getByText("Endpoint: C1420196421");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(node);
    type("C14");
    await pause();
    fireEvent.mouseDown(screen.getByText("Endpoint: C1305486145"));
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: "n1" }));
  });

  it("clears the suggestions when the box is emptied or shortened", async () => {
    stubFetch(() => ({ body: { nodes: [account("n1", "C1305486145")], more: false } }));
    mount();
    const box = type("C13");
    await pause();
    screen.getByText("Endpoint: C1305486145");
    fireEvent.change(box, { target: { value: "C" } });
    await pause(10);
    expect(screen.queryByText("Endpoint: C1305486145")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Type at least 2 characters to search.");
    fireEvent.change(box, { target: { value: "" } });
    await pause(10);
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("GlobalSearch: / to search (ADR-097 step 1)", () => {
  it("/ anywhere outside a text field moves focus to the search box", () => {
    render(<GlobalSearch investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" onSelect={() => undefined} />);
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: /Search entities/ }));
  });

  it("/ goes to the top bar's box, not to a named box that does not take it (ADR-116's From and To)", () => {
    render(
      <>
        <GlobalSearch investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" onSelect={() => undefined} />
        <GlobalSearch
          investigationId="inv-1"
          apiBaseUrl="http://api.test"
          bearerToken="tok"
          onSelect={() => undefined}
          label="Search for From"
          slashFocuses={false}
        />
      </>,
    );
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: /Search entities/ }));
    expect(screen.getByRole("combobox", { name: "Search for From" })).toBeTruthy();
  });

  it("/ typed into another field stays there", () => {
    render(
      <>
        <input aria-label="Note" />
        <GlobalSearch investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" onSelect={() => undefined} />
      </>,
    );
    const note = screen.getByRole("textbox", { name: "Note" });
    note.focus();
    fireEvent.keyDown(note, { key: "/" });
    expect(document.activeElement).toBe(note);
  });
});
