// @vitest-environment jsdom
// ADR-124 decision 2, "a view pushed past the cap" (U6b round 2), as ADR-144 changed it: the dialog a
// reader is shown when the server says their own view of the case is past a cap. Two ways out: save
// a smaller view of the case as a private case view and open it (`save_as_view`: entity types from
// the ontology and never from the case's contents, a date window, or both), or try again (a resync
// with no last sequence). The only figure on it is the reader's own.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LimitExceeded } from "./models";
import { ViewOverCapDialog } from "./ViewOverCapDialog";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const wouldBe: LimitExceeded = {
  error: "limit_exceeded",
  cap_kind: "nodes",
  cap: 50_000,
  would_be: 50_001,
  options: ["save_as_view", "filter", "promote_to_batch"],
};
const ONTOLOGY_TYPES = ["Person", "Vehicle", "Organisation"];
const VIEW = { id: "v1", case_id: "c1", name: "Smaller view of this case", created_by: "a", created_at: "2026-11-08T10:00:00Z", shared: false, chosen: null };
const NODE = { id: "n1", type: "Person" };
const OPENED = { view: VIEW, nodes: [NODE], edges: [], layout: {}, missing: 0 };

type Call = { url: string; method: string; body: unknown; auth: string | undefined };

/** The Conduit's view routes: saving answers 201 with the view, opening answers `opening`, and a
 * delete answers 204. Every call is kept. */
function conduit(
  opening: { status: number; body: unknown } = { status: 200, body: OPENED },
  saving = { status: 201, body: VIEW as unknown },
  deleting = 204,
) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      calls.push({
        url,
        method,
        body: init.body ? JSON.parse(init.body as string) : undefined,
        auth: (init.headers as Record<string, string> | undefined)?.Authorization,
      });
      if (method === "POST") return new Response(JSON.stringify(saving.body), { status: saving.status });
      if (method === "DELETE") return new Response(deleting === 204 ? null : "{}", { status: deleting });
      return new Response(JSON.stringify(opening.body), { status: opening.status });
    }),
  );
  return calls;
}

const saves = (calls: Call[]) => calls.filter((c) => c.method === "POST");

function open(calls: Call[] = conduit(), cap: Partial<LimitExceeded> = {}) {
  const onTryAgain = vi.fn();
  const onViewOpened = vi.fn();
  const onClose = vi.fn();
  render(
    <ViewOverCapDialog
      wouldBe={{ ...wouldBe, ...cap }}
      entityTypes={ONTOLOGY_TYPES}
      apiBaseUrl="http://api.invalid"
      bearerToken="token"
      investigationId="c1"
      onTryAgain={onTryAgain}
      onViewOpened={onViewOpened}
      onClose={onClose}
    />,
  );
  return { calls, onTryAgain, onViewOpened, onClose };
}

describe("the dialog", () => {
  it("says the reader's own figure in the canvas limit's words, and no other number", () => {
    open();
    const dialog = screen.getByRole("dialog", { name: "Your view of this case is too large" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.textContent).toContain(
      "Too many for the canvas: 50,001 nodes against a limit of 50,000.",
    );
    expect(dialog.textContent?.replace(/50,00[01]/g, "")).not.toMatch(/\d/);
    expect(within(dialog).getByRole("button", { name: "Save as a view" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("names links when it is the link cap", () => {
    cleanup();
    render(
      <ViewOverCapDialog
        wouldBe={{ ...wouldBe, cap_kind: "edges", cap: 250_000, would_be: 250_004 }}
        entityTypes={ONTOLOGY_TYPES}
        apiBaseUrl="http://api.invalid"
        bearerToken="token"
        investigationId="c1"
        onTryAgain={() => {}}
        onViewOpened={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole("dialog").textContent).toContain("250,004 links against a limit of 250,000");
  });

  it("Try again asks for a resync, once", () => {
    const { onTryAgain } = open();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onTryAgain).toHaveBeenCalledTimes(1);
  });

  it("Escape closes it, as the other dialogs close", () => {
    const { onClose } = open();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("holds focus: Tab from the last control goes to the first and Shift+Tab back", () => {
    open();
    const dialog = screen.getByRole("dialog");
    const controls = Array.from(
      dialog.querySelectorAll<HTMLElement>("button, input, [href], select, textarea"),
    ).filter((el) => !el.hasAttribute("disabled"));
    controls[controls.length - 1]?.focus();
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Tab" });
    expect(document.activeElement).toBe(controls[0]);
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(controls[controls.length - 1]);
  });

  it("starts with focus inside it", () => {
    open();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });
});

describe("saving a smaller view", () => {
  function openForm() {
    fireEvent.click(screen.getByRole("button", { name: "Save as a view" }));
  }

  it("offers the ontology's entity types and nothing else", async () => {
    open();
    openForm();
    const group = screen.getByRole("group", { name: "Entity types" });
    const offered = within(group)
      .getAllByRole("checkbox")
      .map((box) => (box as HTMLInputElement).labels?.[0]?.textContent);
    expect(offered).toEqual(ONTOLOGY_TYPES);
  });

  it("saves the chosen types and window as a private filtered view, then opens it", async () => {
    const { calls, onViewOpened } = open();
    openForm();
    fireEvent.change(screen.getByLabelText("View name"), { target: { value: "People this quarter" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));

    await waitFor(() => expect(onViewOpened).toHaveBeenCalledWith(OPENED));
    const [save, opening] = calls;
    expect(save?.url).toBe("http://api.invalid/v1/investigations/c1/views");
    expect(save?.method).toBe("POST");
    expect(save?.body).toEqual({
      name: "People this quarter",
      filter: { entity_types: ["Person"], valid_from: "2026-01-01T00:00:00Z", valid_to: "2026-03-31T23:59:59Z" },
    });
    expect(save?.auth).toBe("Bearer token");
    expect(opening?.url).toBe("http://api.invalid/v1/investigations/c1/views/v1");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  });

  it("sends types alone", async () => {
    const { calls } = open();
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Vehicle" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    await waitFor(() => expect(saves(calls)).toHaveLength(1));
    expect((saves(calls)[0]?.body as { filter: unknown }).filter).toEqual({ entity_types: ["Vehicle"] });
  });

  it("asks for a choice, and sends nothing, when none is made", async () => {
    const { calls } = open();
    openForm();
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    expect(screen.getByRole("alert").textContent).toBe("Choose entity types, a date window, or both.");
    expect(calls).toHaveLength(0);
  });

  it("on limit_exceeded shows the filtered figure, keeps no view, and lets the reader narrow again", async () => {
    const filtered = { ...wouldBe, would_be: 50_020 };
    const { calls, onViewOpened } = open(conduit({ status: 409, body: filtered }));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Too many for the canvas: 50,020 nodes against a limit of 50,000. No view was kept. Narrow the choice and try again.",
    );
    expect(onViewOpened).not.toHaveBeenCalled();
    expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/views/v1"))).toBe(true);
    expect((screen.getByRole("checkbox", { name: "Person" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Vehicle" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    await waitFor(() => expect(saves(calls)).toHaveLength(2));
  });

  it("says nothing matched, and keeps no view, when the view opens empty", async () => {
    const { calls } = open(conduit({ status: 200, body: { ...OPENED, nodes: [] } }));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Organisation" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Nothing matched that choice. No view was kept. Choose other types or dates.",
    );
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("says the view is still there, and where to delete it, when removing it fails", async () => {
    const { calls } = open(conduit({ status: 409, body: { ...wouldBe, would_be: 50_020 } }, undefined, 500));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      'Too many for the canvas: 50,020 nodes against a limit of 50,000. The view "Smaller view of this case" was saved and could not be removed: delete it from Views in this case. Narrow the choice and try again.',
    );
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("on a refused save says so and opens nothing", async () => {
    const { calls, onViewOpened } = open(conduit(undefined, { status: 500, body: {} }));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "The view could not be saved (500). Nothing was saved; try again.",
    );
    expect(onViewOpened).not.toHaveBeenCalled();
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(0);
  });
});

describe("a date window alone", () => {
  const WINDOW_ALONE =
    "A date window selects links, not nodes, so on its own it cannot bring a view with too many nodes under the limit. Choose entity types as well.";

  function openForm() {
    fireEvent.click(screen.getByRole("button", { name: "Save as a view" }));
  }

  it("is said plainly when the cap breached is nodes", () => {
    open();
    openForm();
    expect(screen.getByRole("dialog").textContent).toContain(WINDOW_ALONE);
  });

  it("is not sent when the cap breached is nodes: the reader is told why", () => {
    const { calls } = open();
    openForm();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    expect(screen.getByRole("alert").textContent).toBe(WINDOW_ALONE);
    expect(calls).toHaveLength(0);
  });

  it("is a real choice when the cap breached is links, and nothing is said against it", async () => {
    const { calls } = open(conduit(), { cap_kind: "edges", cap: 250_000, would_be: 250_004 });
    openForm();
    expect(screen.getByRole("dialog").textContent).not.toContain("cannot bring");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    await waitFor(() => expect(saves(calls)).toHaveLength(1));
  });

  it("is sent with types when the cap breached is nodes", async () => {
    const { calls } = open();
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and open the view" }));
    await waitFor(() => expect(saves(calls)).toHaveLength(1));
  });
});

describe("focus that leaves the dialog", () => {
  it("is brought back inside it", () => {
    open();
    const outside = document.createElement("input");
    document.body.appendChild(outside);
    outside.focus();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
    outside.remove();
  });

  it("for an expansion the cap refused: its own title and reason, the cap's figure, the save, and no Try again", async () => {
    // spec/00 §4's cap choices on the canvas's expand (rule 2): the refused expansion is not the case's view
    // grown past the cap, so the dialog says what was refused and offers no resync.
    const calls = conduit();
    render(
      <ViewOverCapDialog
        wouldBe={{ ...wouldBe, cap: 5_000, would_be: 6_210 }}
        entityTypes={ONTOLOGY_TYPES}
        apiBaseUrl="http://api.invalid"
        bearerToken="token"
        investigationId="c1"
        title="This expansion is too large"
        why="Expanding Ann Bell would take the canvas past what it can hold. Nothing has been added. You can save a smaller view of the case, private to you, and open that."
        onViewOpened={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "This expansion is too large" })).toBeTruthy();
    expect(screen.getByText("Too many for the canvas: 6,210 nodes against a limit of 5,000.")).toBeTruthy();
    expect(screen.getByText(/Expanding Ann Bell would take the canvas past what it can hold\. Nothing has been added\./)).toBeTruthy();
    expect(screen.queryByText(/Work in this case by others/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save as a view" }));
    expect(screen.getByRole("group", { name: "Entity types" })).toBeTruthy();
    expect(calls).toEqual([]);
  });
});
