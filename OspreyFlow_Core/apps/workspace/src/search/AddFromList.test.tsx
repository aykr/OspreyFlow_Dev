// @vitest-environment jsdom
// Add many from a list (ADR-128 decision 1, B2): the paste box and the file, the count, and the
// confirm. Nothing is added until the analyst has seen the count and chosen; cancelling adds nothing;
// what is added is what was counted; a refusal is in words. The Glass is given counts and a delta,
// never an identifier.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddFromList } from "./AddFromList";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const COUNTS = { read: 40, found: 38, matched_nothing: 2, repeated: 1 };
const DELTA = { seq: 9, op: "add", nodes: [{ id: "n1" }, { id: "n2" }, { id: "n3" }], edges: [] };

type Request = { confirm: boolean; with_links: boolean; identifiers: string[] };

function stub(reply: (body: Request) => { status?: number; body: unknown }): { sent: Request[] } {
  const sent: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Request;
      sent.push(body);
      const { status = 200, body: answer } = reply(body);
      return { ok: status < 300, status, json: async () => answer };
    }),
  );
  return { sent };
}

const normal = (body: Request) => ({
  body: { counts: COUNTS, added: body.confirm ? { delta: DELTA, links_among: "not_asked" } : null },
});

function mount(onApplyDelta = vi.fn(), onClose = vi.fn()) {
  render(
    <AddFromList
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="inv-1"
      onApplyDelta={onApplyDelta}
      onClose={onClose}
    />,
  );
  return { onApplyDelta, onClose };
}

const box = () => screen.getByRole("textbox", { name: /identifiers/i });
const paste = (text: string) => fireEvent.change(box(), { target: { value: text } });
const press = (name: string | RegExp) => fireEvent.click(screen.getByRole("button", { name }));

describe("the count comes first", () => {
  it("offers a paste box and a file, and cannot count nothing", () => {
    mount();
    expect(box()).toBeTruthy();
    expect(screen.getByLabelText(/\.txt or \.csv file/i)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Count" }) as HTMLButtonElement).disabled).toBe(true);
    paste("Z1234ZZ");
    expect((screen.getByRole("button", { name: "Count" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("counts what was pasted, says the four figures, and adds nothing", async () => {
    const { sent } = stub(normal);
    const { onApplyDelta } = mount();
    paste("Z1234ZZ\n07700 900123");
    press("Count");
    expect((await screen.findByRole("status")).textContent).toBe(
      "40 identifiers read. 38 found. 2 matched nothing you can see. 1 repeated.",
    );
    expect(sent).toEqual([{ identifiers: ["Z1234ZZ\n07700 900123"], confirm: false, with_links: false }]);
    expect(onApplyDelta).not.toHaveBeenCalled();
  });

  it("offers no add until a count has been seen", () => {
    mount();
    paste("Z1234ZZ");
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add with all links" })).toBeNull();
  });

  it("forgets a count when the text changes, so what is added is what was counted", async () => {
    stub(normal);
    mount();
    paste("Z1234ZZ");
    press("Count");
    await screen.findByRole("status");
    paste("Z1234ZZ\nZ2345ZZ");
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });

  it("offers no add when nothing was found", async () => {
    stub(() => ({ body: { counts: { read: 2, found: 0, matched_nothing: 2, repeated: 0 }, added: null } }));
    mount();
    paste("Z9999ZZ NOBODY");
    press("Count");
    await screen.findByRole("status");
    expect((screen.getByRole("button", { name: "Add" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Add with all links" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("the confirm", () => {
  it("adds without links by default, draws the delta and says how many nodes", async () => {
    const { sent } = stub(normal);
    const { onApplyDelta } = mount();
    paste("Z1234ZZ");
    press("Count");
    await screen.findByRole("status");
    press("Add");
    await waitFor(() => expect(onApplyDelta).toHaveBeenCalledWith(DELTA));
    expect(sent[1]).toEqual({ identifiers: ["Z1234ZZ"], confirm: true, with_links: false });
    expect((await screen.findByText("3 added.")).getAttribute("role")).toBe("status");
    // Done: the count is gone, so a second press cannot add the list twice.
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });

  it("adds with all the links when that is chosen", async () => {
    const { sent } = stub(normal);
    const { onApplyDelta } = mount();
    paste("Z1234ZZ");
    press("Count");
    await screen.findByRole("status");
    press("Add with all links");
    await waitFor(() => expect(onApplyDelta).toHaveBeenCalledTimes(1));
    expect(sent[1]).toEqual({ identifiers: ["Z1234ZZ"], confirm: true, with_links: true });
  });

  it("past the canvas's limit says so with the figure, adds nothing, and keeps the count to choose again", async () => {
    stub((body) =>
      body.confirm
        ? { status: 409, body: { error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50002, options: ["branch", "filter", "promote_to_batch"] } }
        : { body: { counts: COUNTS, added: null } },
    );
    const { onApplyDelta } = mount();
    paste("Z1234ZZ");
    press("Count");
    await screen.findByRole("status");
    press("Add");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Too many for the canvas: 50,002 nodes against a limit of 50,000. Nothing was added.");
    expect(alert.textContent).toContain("branch the case");
    expect(onApplyDelta).not.toHaveBeenCalled();
  });
});

describe("cancelling", () => {
  it("adds nothing, clears the box and the count, and closes", async () => {
    const { sent } = stub(normal);
    const { onApplyDelta, onClose } = mount();
    paste("Z1234ZZ");
    press("Count");
    await screen.findByRole("status");
    press("Cancel");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect((box() as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByRole("status")).toBeNull();
    expect(sent).toHaveLength(1);
    expect(onApplyDelta).not.toHaveBeenCalled();
  });

  it("is what Escape does", async () => {
    stub(normal);
    const { onClose } = mount();
    paste("Z1234ZZ");
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect((box() as HTMLTextAreaElement).value).toBe("");
  });
});

describe("a refusal", () => {
  it("names the limit of 5,000 when the list is longer", async () => {
    stub(() => ({ status: 413, body: { error: "too_many_identifiers", cap: 5000, received: 5001 } }));
    mount();
    paste("Z1234ZZ");
    press("Count");
    expect((await screen.findByRole("alert")).textContent).toContain("5,001 identifiers is more than one request reads, which is 5,000.");
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });
});

describe("a file", () => {
  it("fills the box with a .csv's first column, for the analyst to see and count", async () => {
    stub(normal);
    mount();
    const file = new File(["id,name\nZ1234ZZ,Smith\nZ2345ZZ,Jones\n"], "cohort.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/\.txt or \.csv file/i), { target: { files: [file] } });
    await waitFor(() => expect((box() as HTMLTextAreaElement).value).toBe("id\nZ1234ZZ\nZ2345ZZ"));
    expect(screen.getByText("Read cohort.csv. Count it to see what it holds.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Count" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("fills the box with a .txt as it is", async () => {
    mount();
    const file = new File(["Z1234ZZ\nZ2345ZZ\n"], "cohort.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText(/\.txt or \.csv file/i), { target: { files: [file] } });
    await waitFor(() => expect((box() as HTMLTextAreaElement).value).toBe("Z1234ZZ\nZ2345ZZ"));
  });
});
