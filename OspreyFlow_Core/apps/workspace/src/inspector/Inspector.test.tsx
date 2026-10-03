// @vitest-environment jsdom
import Graph from "graphology";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import { Inspector, type InspectorProps } from "./Inspector";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const link = {
  edge: {
    id: "e7",
    type: "ASSOCIATED_WITH",
    source: "a",
    target: "b",
    occurrences: 1,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
  } as unknown as Edge,
  source: undefined,
  target: undefined,
  directed: true,
};

const assessment: NonNullable<InspectorProps["assessment"]> = {
  apiBaseUrl: "http://api.test",
  bearerToken: "tok",
  investigationId: "inv-1",
  workingSetGraph: new Graph(),
  onHighlightNodes: () => undefined,
};

function stubNotes() {
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () =>
      url.includes("/notes") ? { notes: [] } : url.includes("/history") ? { changes: [], truncated: false } : {},
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Inspector — a selected link", () => {
  it("shows the link's details and a Notes section for that link", async () => {
    const fetchMock = stubNotes();
    render(<Inspector node={null} link={link} assessment={assessment} />);
    expect(screen.getByText("ASSOCIATED_WITH")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Notes" })).toBeTruthy();
    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain(
        "http://api.test/v1/investigations/inv-1/links/e7/notes",
      ),
    );
    expect(await screen.findByText("No notes on this link yet.")).toBeTruthy();
  });

  it("offers no Notes when the case is not wired up (no investigation to keep them in)", () => {
    stubNotes();
    render(<Inspector node={null} link={link} />);
    expect(screen.getByText("ASSOCIATED_WITH")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull();
  });

  it("shows no link Notes for a selected node", () => {
    const fetchMock = stubNotes();
    const node = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(<Inspector node={node} assessment={assessment} />);
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/notes"))).toBe(false);
  });
  it("offers a change and a history for an ordinary link, once the ends and the ontology are known (ADR-080)", async () => {
    stubNotes();
    const person = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(
      <Inspector
        node={null}
        link={{ ...link, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ edgeTypes: [], openChangeSignal: 0, openNoteSignal: 0, onChanged: () => undefined }}
      />,
    );
    expect(screen.getByRole("button", { name: "Change this link…" })).toBeTruthy();
    expect(await screen.findByRole("region", { name: "Change history" })).toBeTruthy();
  });

  it("offers neither to a same-as link: that is confirmed or marked, not edited", async () => {
    stubNotes();
    const person = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(
      <Inspector
        node={null}
        link={{ ...link, edge: { ...link.edge, type: "SAME_AS" }, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ edgeTypes: [], openChangeSignal: 0, openNoteSignal: 0, onChanged: () => undefined }}
      />,
    );
    expect(screen.queryByRole("button", { name: "Change this link…" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Change history" })).toBeNull();
    expect(screen.getByRole("region", { name: "Notes" })).toBeTruthy();
  });
});
