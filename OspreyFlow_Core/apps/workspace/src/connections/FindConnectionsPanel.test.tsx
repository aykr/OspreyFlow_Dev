// @vitest-environment jsdom
// ADR-116: Find connections. The two ends by search or from the canvas's selection; the fewest
// degrees said in words; widened one degree at a time to eight; ten of more said as such (rule 2); a
// route put on the canvas with its nodes marked by their degree from From; a refusal said in words.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node, Path } from "../../../../packages/schemas/generated";
import { SUGGEST_PAUSE_MS } from "../search/GlobalSearch";
import { FindConnectionsPanel } from "./FindConnectionsPanel";

function node(id: string, name: string): Node {
  return {
    id,
    type: "Person",
    properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  } as unknown as Node;
}

const NAMES: Record<string, string> = { a: "Ada", b: "Ben", c: "Cy", d: "Dee", x: "Xan" };
const ADA = node("a", "Ada");
const DEE = node("d", "Dee");

function route(...ids: string[]): Path {
  return {
    nodes: ids.map((id) => node(id, NAMES[id] ?? id)),
    edges: ids.slice(1).map((id, i) => ({ id: `${ids[i]}-${id}`, type: "ASSOCIATE_OF", source: ids[i], target: id }) as unknown as Edge),
    length: ids.length - 1,
  };
}

interface Asked {
  path: string;
  body: Record<string, unknown>;
}

/** The Conduit: suggest finds Ada for "Ad" and Dee for "De"; connections answers from `answers`. */
function serve(answers: (body: Record<string, unknown>) => { status?: number; body?: unknown }): Asked[] {
  const asked: Asked[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      asked.push({ path, body });
      if (path === "suggest") {
        const nodes = String(body.query).startsWith("Ad") ? [ADA] : String(body.query).startsWith("De") ? [DEE] : [];
        return new Response(JSON.stringify({ nodes, more: false }));
      }
      if (path === "seed") return new Response(JSON.stringify({ delta: { op: "add", seq: 1 } }));
      const answer = answers(body);
      return new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200 });
    }),
  );
  return asked;
}

const onCanvas = new Set<string>();
const props = () => ({
  apiBaseUrl: "http://api",
  bearerToken: "t",
  investigationId: "c1",
  canvas: { hasNode: (id: string) => onCanvas.has(id), hasEdge: (id: string) => onCanvas.has(id) },
  onDelta: vi.fn(),
  onMark: vi.fn(),
  onClearMarks: vi.fn(),
});

async function settle(ms = SUGGEST_PAUSE_MS): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function choose(end: "From" | "To", typed: string, shown: string): Promise<void> {
  const box = screen.getByRole("combobox", { name: `Search for ${end}` });
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: typed } });
  await settle();
  fireEvent.mouseDown(screen.getByRole("option", { name: `Person: ${shown}` }));
}

async function find(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Find connections" }));
  await settle(0);
}

beforeEach(() => {
  vi.useFakeTimers();
  onCanvas.clear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("choosing the two ends", () => {
  it("takes each end from a search, and asks for the fewest degrees with no degree given", async () => {
    const asked = serve(() => ({ body: { degree: 3, paths: [route("a", "b", "c", "d")], more: false, searched_to: 3 } }));
    render(<FindConnectionsPanel {...props()} selected={null} />);
    await choose("From", "Ad", "Ada");
    await choose("To", "De", "Dee");
    expect(screen.getByText("From: Ada")).toBeTruthy();
    expect(screen.getByText("To: Dee")).toBeTruthy();
    await find();
    expect(asked.filter((a) => a.path === "connections").map((a) => a.body)).toEqual([{ source: "a", target: "d" }]);
    expect(screen.getByRole("status").textContent).toBe("Ada and Dee are 3 degrees apart.");
    const group = screen.getByRole("region", { name: "1 route at 3 degrees" });
    expect(within(group).getByText("Ada → Ben → Cy → Dee")).toBeTruthy();
  });

  it("takes an end from the node selected on the canvas", async () => {
    serve(() => ({ body: { degree: 1, paths: [route("a", "d")], more: false, searched_to: 1 } }));
    const { rerender } = render(<FindConnectionsPanel {...props()} selected={null} />);
    const useForFrom = screen.getByRole("button", { name: "Use the selected node as From" });
    expect(useForFrom.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(useForFrom);
    expect(screen.queryByText("From: Ada")).toBeNull();
    rerender(<FindConnectionsPanel {...props()} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as From" }));
    rerender(<FindConnectionsPanel {...props()} selected={DEE} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as To" }));
    expect(screen.getByText("From: Ada")).toBeTruthy();
    expect(screen.getByText("To: Dee")).toBeTruthy();
  });

  it("will not search from a node to itself, and says why", async () => {
    const asked = serve(() => ({}));
    const { rerender } = render(<FindConnectionsPanel {...props()} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as From" }));
    rerender(<FindConnectionsPanel {...props()} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as To" }));
    expect(screen.getByText("From and To are the same node.")).toBeTruthy();
    const findButton = screen.getByRole("button", { name: "Find connections" });
    expect(findButton.getAttribute("aria-disabled")).toBe("true");
    await find();
    expect(asked.filter((a) => a.path === "connections")).toEqual([]);
  });
});

describe("the routes, widened one degree at a time", () => {
  async function ready(answers: Parameters<typeof serve>[0]): Promise<Asked[]> {
    const asked = serve(answers);
    const { rerender } = render(<FindConnectionsPanel {...props()} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as From" }));
    rerender(<FindConnectionsPanel {...props()} selected={DEE} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as To" }));
    await find();
    return asked;
  }

  it("widens by one degree, keeping the shorter routes in their own group, up to eight", async () => {
    const asked = await ready((body) => {
      const degree = (body.degree as number | undefined) ?? 2;
      return { body: { degree, paths: [route("a", "x", "d")].slice(0, degree === 2 ? 1 : 0), more: false, searched_to: degree } };
    });
    for (const next of [3, 4, 5, 6, 7, 8]) {
      fireEvent.click(screen.getByRole("button", { name: `Show routes at ${next} degrees` }));
      await settle(0);
    }
    expect(asked.filter((a) => a.path === "connections").map((a) => a.body.degree)).toEqual([undefined, 3, 4, 5, 6, 7, 8]);
    expect(screen.getByRole("region", { name: "1 route at 2 degrees" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "No routes at 8 degrees" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Show routes at 9 degrees/ })).toBeNull();
  });

  it("says ten of more than ten, never ten as all of them (rule 2)", async () => {
    const ten = Array.from({ length: 10 }, () => route("a", "x", "d"));
    await ready(() => ({ body: { degree: 2, paths: ten, more: true, searched_to: 2 } }));
    expect(screen.getByRole("region", { name: "10 of more than 10 routes at 2 degrees" })).toBeTruthy();
  });

  it("says when nothing connects them within six degrees, and offers the seventh", async () => {
    await ready(() => ({ body: { degree: null, paths: [], more: false, searched_to: 6 } }));
    expect(screen.getByRole("status").textContent).toBe("Ada and Dee are not connected within 6 degrees.");
    expect(screen.getByRole("button", { name: "Show routes at 7 degrees" })).toBeTruthy();
  });

  it("says a search that did not complete in words", async () => {
    await ready(() => ({ status: 503 }));
    expect(screen.getByRole("alert").textContent).toBe("The search for connections failed (503). Try again.");
  });
});

describe("a route put on the canvas", () => {
  it("is seeded, drawn, its nodes marked by degree from From, and then said to be on the canvas", async () => {
    const asked = serve(() => ({ body: { degree: 2, paths: [route("a", "x", "d")], more: false, searched_to: 2 } }));
    const given = props();
    const { rerender } = render(<FindConnectionsPanel {...given} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as From" }));
    rerender(<FindConnectionsPanel {...given} selected={DEE} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as To" }));
    await find();
    fireEvent.click(screen.getByRole("button", { name: "Add route 1 at 2 degrees to the canvas" }));
    await settle(0);
    const seeded = asked.find((a) => a.path === "seed")!;
    expect((seeded.body.nodes as Node[]).map((n) => n.id)).toEqual(["a", "x", "d"]);
    expect(given.onDelta).toHaveBeenCalledWith({ op: "add", seq: 1 });
    expect([...(given.onMark.mock.calls[0]![0] as Map<string, number>)]).toEqual([["a", 0], ["x", 1], ["d", 2]]);
    expect(screen.queryByRole("button", { name: "Add route 1 at 2 degrees to the canvas" })).toBeNull();
    expect(screen.getByText("On the canvas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear the degree marks" }));
    expect(given.onClearMarks).toHaveBeenCalled();
  });

  it("is said to be on the canvas when it is already there, and offers no Add", async () => {
    for (const id of ["a", "x", "d", "a-x", "x-d"]) onCanvas.add(id);
    serve(() => ({ body: { degree: 2, paths: [route("a", "x", "d")], more: false, searched_to: 2 } }));
    const { rerender } = render(<FindConnectionsPanel {...props()} selected={ADA} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as From" }));
    rerender(<FindConnectionsPanel {...props()} selected={DEE} />);
    fireEvent.click(screen.getByRole("button", { name: "Use the selected node as To" }));
    await find();
    expect(screen.queryByRole("button", { name: /Add route 1/ })).toBeNull();
    expect(screen.getByText("On the canvas")).toBeTruthy();
  });
});
