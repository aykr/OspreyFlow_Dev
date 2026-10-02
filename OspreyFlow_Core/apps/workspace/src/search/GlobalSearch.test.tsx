// @vitest-environment jsdom
//
// The search box as the analyst types (ADR-059). Seen, 2 October 2026: typing `C` or part of an
// account id found nothing, because the box asked for an exact match. It now asks `/v1/suggest`
// from the third character, after a pause, ignores an answer to a question already superseded,
// says when more matched than are shown, and says when the Conduit could not answer.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { GlobalSearch, SUGGEST_MIN_CHARS, SUGGEST_PAUSE_MS } from "./GlobalSearch";

function account(id: string, value: string): Node {
  return { id, type: "Endpoint", properties: { value_normalised: value } } as unknown as Node;
}

type Reply = { status?: number; body?: unknown; delayMs?: number };

function stubFetch(reply: (query: string) => Reply): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    if (!url.endsWith("/v1/suggest") || init?.method !== "POST") throw new Error(`unexpected request ${url}`);
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
  render(<GlobalSearch apiBaseUrl="http://api" bearerToken="t" onSelect={onSelect} />);
  return onSelect;
}

describe("GlobalSearch as the analyst types", () => {
  it("asks nothing until three characters are typed", async () => {
    const mock = stubFetch(() => ({}));
    mount();
    type("C1");
    await pause(SUGGEST_PAUSE_MS * 4);
    expect(SUGGEST_MIN_CHARS).toBe(3);
    expect(mock).not.toHaveBeenCalled();
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
    fireEvent.change(box, { target: { value: "C1" } });
    await pause(10);
    expect(screen.queryByText("Endpoint: C1305486145")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
