// @vitest-environment jsdom
// ADR-115 E6 (the reference's welcome panel): over the canvas's top left, what the canvas holds, the
// case's three latest history steps to pick up from (each restores as the History drawer's do), and
// the keys worth knowing — each one the Glass really has. Closing it is remembered per person.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { welcomeDismissed, setWelcomeDismissed, WorkspaceWelcome } from "./WorkspaceWelcome";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const STEPS = [
  { id: "s1", label: "Expanded HALE, Marcus by one hop", created_at: "2026-10-12T16:42:00Z", node_count: 25, edge_count: 30 },
  { id: "s2", label: "Branched 2 entities into a new case", created_at: "2026-10-12T16:10:00Z", node_count: 2, edge_count: 1 },
  { id: "s3", label: "Ran community detection", created_at: "2026-10-08T11:05:00Z", node_count: 20, edge_count: 22 },
  { id: "s4", label: "Older", created_at: "2026-10-01T11:05:00Z", node_count: 1, edge_count: 0 },
];

function shown(onRestored = vi.fn(), onClose = vi.fn()) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    init?.method === "POST" ? new Response(JSON.stringify({ seq: 9, nodes: [], edges: [] })) : new Response(JSON.stringify(STEPS)),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <WorkspaceWelcome apiBaseUrl="http://api" bearerToken="t" investigationId="c1" nodeCount={25}
                      onRestored={onRestored} onClose={onClose} now={new Date("2026-10-13T09:00:00Z")} />,  // prettier-ignore
  );
  return { fetchMock, onRestored, onClose };
}

describe("the workspace's welcome panel", () => {
  it("says what the canvas holds, and how to bring the panel back", () => {
    shown();
    const panel = within(screen.getByRole("dialog", { name: "Welcome back" }));
    expect(panel.getByText("The canvas shows the 25 entities you were working on last.")).toBeTruthy();
  });

  it("offers the three latest history steps, and restores one as the History drawer does", async () => {
    const { fetchMock, onRestored, onClose } = shown();
    const list = within(await screen.findByRole("list", { name: "Pick up where you left off" }));
    expect(list.getAllByRole("button").map((b) => b.textContent)).toEqual([
      expect.stringContaining("Expanded HALE, Marcus by one hop"),
      expect.stringContaining("Branched 2 entities into a new case"),
      expect.stringContaining("Ran community detection"),
    ]);
    fireEvent.click(list.getAllByRole("button")[0]!);
    await waitFor(() => expect(onRestored).toHaveBeenCalledWith({ seq: 9, nodes: [], edges: [] }));
    expect(fetchMock).toHaveBeenCalledWith("http://api/v1/investigations/c1/history/s1", expect.objectContaining({ method: "POST" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("lists the keys worth knowing, each a key the Glass has, in key caps", () => {
    shown();
    const keys = within(screen.getByRole("list", { name: "Keys worth knowing" }));
    const rows = keys.getAllByRole("listitem").map((li) => [li.querySelector("kbd")?.textContent, li.textContent]);
    expect(rows.map(([k]) => k)).toEqual(["/", "←→", "Enter", "F", "Esc", "?"]);
    expect(rows[2]![1]).toContain("Expand the focused node by one hop");
  });

  it("closes from its own button", () => {
    const { onClose } = shown();
    fireEvent.click(screen.getByRole("button", { name: "Close the welcome panel" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("whether the welcome panel was closed", () => {
  it("is remembered per person, and is false for someone who has not closed it", () => {
    expect(welcomeDismissed("u1")).toBe(false);
    setWelcomeDismissed("u1", true);
    expect(welcomeDismissed("u1")).toBe(true);
    expect(welcomeDismissed("u2")).toBe(false);
  });
});
