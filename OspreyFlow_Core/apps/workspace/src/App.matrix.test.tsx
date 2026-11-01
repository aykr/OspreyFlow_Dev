// @vitest-environment jsdom
//
// The Matrix view in the real App (`02_GLASS_FRONTEND.md` §2 rule 1 and §6; GDS remediation plan
// A1): reached from the view switch beside Graph and Map, over the same working set, and the
// selection carried both ways — what was selected on the canvas is selected in the Matrix, and what
// is selected in the Matrix is selected on the canvas when the Graph opens again. The canvas is a
// recording stand-in here (it needs WebGL, which jsdom lacks); `keyboard/matrix.spec.ts` drives
// the real canvas in a browser.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import type { GlassCanvasProps } from "./canvas/GlassCanvas";

const canvas = vi.hoisted(() => ({
  props: null as null | Record<string, unknown>,
  mounts: 0,
  handle: {
    focusOnNode: (() => undefined) as (id: string) => void,
    expandNode: (() => undefined) as (id: string) => void,
  },
}));

vi.mock("./canvas/GlassCanvas", async () => {
  const React = await import("react");
  const GlassCanvas = React.forwardRef<unknown, Record<string, unknown>>(function GlassCanvas(props, ref) {
    canvas.props = props;
    React.useImperativeHandle(ref, () => canvas.handle);
    React.useEffect(() => {
      canvas.mounts += 1;
    }, []);
    return null;
  });
  return { GlassCanvas };
});
vi.mock("./map/MapView", () => ({ MapView: () => null }));
vi.mock("./timeline/Timeline", () => ({ Timeline: () => null }));

// The working set the App makes, already holding three people and two links — as if the stream had
// delivered them. Only this case's reader's view: nothing withheld is in it, and nothing else is.
vi.mock("./workingset/store", async () => {
  const actual = await vi.importActual<typeof import("./workingset/store")>("./workingset/store");
  const { makeEdge, makeNode } = await import("./testing/fixtures");
  return {
    ...actual,
    createWorkingSet: () => {
      const ws = actual.createWorkingSet();
      ws.store.getState().applyDelta({
        seq: 1,
        op: "snapshot",
        nodes: [
          makeNode("p1", { properties: { family_name: "OKAFOR", given_names: "Callum" } }),
          makeNode("p2", { properties: { family_name: "ADEYEMI", given_names: "Tola" } }),
          makeNode("p3", {
            properties: { family_name: "BRENNAN" },
            provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" },
          }),
        ],
        edges: [makeEdge("l1", "p1", "p2"), makeEdge("l2", "p1", "p3")],
      });
      return ws;
    },
  };
});

vi.mock("./auth/userManager", async () => {
  const actual = await vi.importActual<typeof import("./auth/userManager")>("./auth/userManager");
  return {
    ...actual,
    isSignInRedirectCallback: vi.fn(() => true),
    completeSignInFromRedirect: vi.fn(async () => ({
      access_token: "good-token",
      profile: { sub: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
    })),
    clearRedirectCallbackParams: vi.fn(),
    getUserManager: vi.fn(() => ({ signinRedirect: vi.fn() }) as never),
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
});

vi.mock("./map/providers", async () => {
  const actual = await vi.importActual<typeof import("./map/providers")>("./map/providers");
  return { ...actual, fetchMapConfig: vi.fn(() => new Promise(() => undefined)) };
});

let App!: typeof AppComponent;
beforeAll(async () => {
  const g = globalThis as { WebGL2RenderingContext?: unknown; WebGLRenderingContext?: unknown };
  g.WebGL2RenderingContext ??= class {};
  g.WebGLRenderingContext ??= class {};
  ({ App } = await import("./App"));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  sessionStorage.clear();
  canvas.props = null;
  canvas.mounts = 0;
});

function holdRequests() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/v1/ontology")) {
      return new Response(JSON.stringify({ edge_types: [], entity_types: [] }), { status: 200 });
    }
    return new Promise<Response>(() => undefined);
  });
}

const viewButton = (name: string) =>
  within(screen.getByRole("group", { name: "View" })).getByRole("button", { name });
const entities = () => screen.getByRole("grid", { name: /^Entities in this view/ });
const rowOf = (name: RegExp) =>
  within(entities()).getAllByRole("row").find((r) => within(r).queryByRole("rowheader", { name }))!;
const props = () => canvas.props as unknown as GlassCanvasProps;

test("the view switch offers the Matrix beside the Graph and the Map", async () => {
  window.history.replaceState({}, "", "/?investigation=case-1");
  holdRequests();
  render(<App />);
  await waitFor(() => expect(canvas.props).not.toBeNull());
  const names = within(screen.getByRole("group", { name: "View" }))
    .getAllByRole("button")
    .map((b) => b.textContent);
  expect(names.slice(0, 3)).toEqual(["Graph", "Map", "Matrix"]);
  fireEvent.click(viewButton("Matrix"));
  expect(viewButton("Matrix").getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("heading", { name: "Matrix" })).toBeTruthy();
  // The same working set, read again from nothing: three people, two links.
  expect(entities().querySelector("caption")?.textContent).toMatch(/^Entities in this view, 3\./);
  expect(within(rowOf(/BRENNAN/)).getByText("Inferred")).toBeTruthy();
});

test("a selection made on the canvas is the Matrix's selection, and the Matrix's goes back to the canvas", async () => {
  window.history.replaceState({}, "", "/?investigation=case-1");
  holdRequests();
  render(<App />);
  await waitFor(() => expect(canvas.props).not.toBeNull());

  // Canvas to Matrix: the canvas reports a selection, as a click on ADEYEMI does.
  act(() => props().onSelectionChange?.(["p2"]));
  fireEvent.click(viewButton("Matrix"));
  expect(rowOf(/ADEYEMI/).getAttribute("aria-selected")).toBe("true");
  expect(rowOf(/OKAFOR/).getAttribute("aria-selected")).toBe("false");

  // Matrix to canvas: select BRENNAN here; the Inspector shows it; the Graph opens with it selected.
  fireEvent.click(within(rowOf(/BRENNAN/)).getByRole("rowheader"));
  expect(rowOf(/BRENNAN/).getAttribute("aria-selected")).toBe("true");
  expect(rowOf(/ADEYEMI/).getAttribute("aria-selected")).toBe("false");
  const mountsBefore = canvas.mounts;
  fireEvent.click(viewButton("Graph"));
  await waitFor(() => expect(canvas.mounts).toBe(mountsBefore + 1));
  expect(props().initialSelectedNodeIds).toEqual(["p3"]);
});

test("Expand and Show on a row go to the Graph and use the canvas's own Expand and centring", async () => {
  window.history.replaceState({}, "", "/?investigation=case-1");
  holdRequests();
  const expandNode = vi.fn();
  const focusOnNode = vi.fn();
  canvas.handle.expandNode = expandNode;
  canvas.handle.focusOnNode = focusOnNode;
  render(<App />);
  await waitFor(() => expect(canvas.props).not.toBeNull());

  fireEvent.click(viewButton("Matrix"));
  fireEvent.click(screen.getByRole("button", { name: "Show OKAFOR, Callum on the graph" }));
  expect(viewButton("Graph").getAttribute("aria-pressed")).toBe("true");
  await waitFor(() => expect(focusOnNode).toHaveBeenCalledWith("p1"));

  fireEvent.click(viewButton("Matrix"));
  fireEvent.click(screen.getByRole("button", { name: "Expand BRENNAN" }));
  expect(viewButton("Graph").getAttribute("aria-pressed")).toBe("true");
  await waitFor(() => expect(expandNode).toHaveBeenCalledWith("p3"));
  expect(props().initialSelectedNodeIds).toEqual(["p3"]);
});
