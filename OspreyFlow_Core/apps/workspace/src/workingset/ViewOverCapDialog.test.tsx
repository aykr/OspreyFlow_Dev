// @vitest-environment jsdom
// ADR-124 decision 2, "a view pushed past the cap" (U6b round 2): the dialog a reader is shown when
// the server says their own view of the case is past a cap. Two ways out: open a filtered branch
// (entity types from the ontology and never from the case's contents, a date window, or both), or
// try again (a resync with no last sequence). The only figure on it is the reader's own.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { branchByFilter } from "./branchByFilter";
import type { LimitExceeded } from "./models";
import { ViewOverCapDialog } from "./ViewOverCapDialog";

afterEach(cleanup);

const wouldBe: LimitExceeded = {
  error: "limit_exceeded",
  cap_kind: "nodes",
  cap: 50_000,
  would_be: 50_001,
  options: ["branch", "filter", "promote_to_batch"],
};
const ONTOLOGY_TYPES = ["Person", "Vehicle", "Organisation"];

function reply(status: number, body: unknown): typeof fetch {
  return vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

function open(
  fetcher: typeof fetch = reply(201, { id: "branch-1", name: "Branch of Case" }),
  cap: Partial<LimitExceeded> = {},
) {
  const onTryAgain = vi.fn();
  const onBranchOpened = vi.fn();
  const onClose = vi.fn();
  render(
    <ViewOverCapDialog
      wouldBe={{ ...wouldBe, ...cap }}
      entityTypes={ONTOLOGY_TYPES}
      apiBaseUrl="http://api.invalid"
      bearerToken="token"
      investigationId="c1"
      onTryAgain={onTryAgain}
      onBranchOpened={onBranchOpened}
      onClose={onClose}
      fetcher={fetcher}
    />,
  );
  return { fetcher, onTryAgain, onBranchOpened, onClose };
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
    expect(within(dialog).getByRole("button", { name: "Open a filtered branch" })).toBeTruthy();
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
        onBranchOpened={() => {}}
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

describe("opening a filtered branch", () => {
  function openForm() {
    fireEvent.click(screen.getByRole("button", { name: "Open a filtered branch" }));
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

  it("sends the chosen types and window, and opens the new case", async () => {
    const { fetcher, onBranchOpened } = open();
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));

    await waitFor(() => expect(onBranchOpened).toHaveBeenCalledWith("branch-1", "Branch of Case"));
    const [url, init] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.invalid/v1/investigations/c1/branch-by-filter");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      entity_types: ["Person"],
      valid_from: "2026-01-01T00:00:00Z",
      valid_to: "2026-03-31T23:59:59Z",
    });
    expect(((init as RequestInit).headers as Record<string, string>).Authorization).toBe("Bearer token");
  });

  it("sends types alone, or a window alone", async () => {
    const { fetcher } = open();
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Vehicle" }));
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const call = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(call[1].body as string);
    expect(body).toEqual({ entity_types: ["Vehicle"] });
  });

  it("asks for a choice, and sends nothing, when none is made", async () => {
    const { fetcher } = open();
    openForm();
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect(screen.getByRole("alert").textContent).toBe("Choose entity types, a date window, or both.");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("on limit_exceeded shows the filtered figure and lets the reader narrow again", async () => {
    const filtered = { ...wouldBe, would_be: 50_020 };
    const { fetcher, onBranchOpened } = open(reply(409, filtered));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Too many for the canvas: 50,020 nodes against a limit of 50,000. Narrow the choice and try again.",
    );
    expect(onBranchOpened).not.toHaveBeenCalled();
    // The form is still there, with the choice kept, and can be sent again.
    expect((screen.getByRole("checkbox", { name: "Person" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Vehicle" }));
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it("on nothing_to_branch says nothing matched", async () => {
    open(reply(422, { error: "nothing_to_branch" }));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Organisation" }));
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Nothing matched that choice. Choose other types or dates.",
    );
  });

  it("on any other failure says so and makes no case", async () => {
    const { onBranchOpened } = open(reply(500, {}));
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Branching failed (500). No case was made. Try again.",
    );
    expect(onBranchOpened).not.toHaveBeenCalled();
  });
});

describe("a date window alone", () => {
  const WINDOW_ALONE =
    "A date window selects links, not nodes, so on its own it cannot bring a view with too many nodes under the limit. Choose entity types as well.";

  function openForm() {
    fireEvent.click(screen.getByRole("button", { name: "Open a filtered branch" }));
  }

  it("is said plainly when the cap breached is nodes", () => {
    open();
    openForm();
    expect(screen.getByRole("dialog").textContent).toContain(WINDOW_ALONE);
  });

  it("is not sent when the cap breached is nodes: the reader is told why", () => {
    const { fetcher } = open();
    openForm();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect(screen.getByRole("alert").textContent).toBe(WINDOW_ALONE);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("is a real choice when the cap breached is links, and nothing is said against it", async () => {
    const { fetcher } = open(undefined, { cap_kind: "edges", cap: 250_000, would_be: 250_004 });
    openForm();
    expect(screen.getByRole("dialog").textContent).not.toContain("cannot bring");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });

  it("is sent with types when the cap breached is nodes", async () => {
    const { fetcher } = open();
    openForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "Person" }));
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });
});

describe("branchByFilter, the request", () => {
  it("answers each outcome as a value, never a throw", async () => {
    const base = { apiBaseUrl: "http://api.invalid", bearerToken: "t", investigationId: "c1", entityTypes: ["Person"] };
    expect(await branchByFilter(reply(201, { id: "b", name: "n" }), base)).toEqual({ ok: true, id: "b", name: "n" });
    expect(await branchByFilter(reply(409, { ...wouldBe, would_be: 7 }), base)).toMatchObject({
      ok: false,
      kind: "limit_exceeded",
    });
    expect(await branchByFilter(reply(422, { error: "nothing_to_branch" }), base)).toEqual({
      ok: false,
      kind: "nothing_matched",
    });
    expect(await branchByFilter(reply(403, {}), base)).toMatchObject({ ok: false, kind: "failed" });
    const down = (async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch;
    expect(await branchByFilter(down, base)).toMatchObject({ ok: false, kind: "failed" });
    expect(await branchByFilter(reply(201, {}), { ...base, entityTypes: undefined })).toEqual({
      ok: false,
      kind: "nothing_chosen",
    });
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
});
