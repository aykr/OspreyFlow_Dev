// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LinkNote } from "../../../../packages/schemas/generated";
import { LinkNotes } from "./LinkNotes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BASE = "http://api.test";

function note(id: string, author: string, body: string, minute: number, mine: boolean): LinkNote {
  return {
    id,
    investigation_id: "inv-1",
    edge_id: "e1",
    author,
    body,
    created_at: `2026-10-01T09:${String(minute).padStart(2, "0")}:00Z`,
    edited_at: null,
    mine,
  };
}

interface Call {
  method: string;
  url: string;
  body: unknown;
}

/** A small stand-in for the notes routes, holding notes in memory and refusing what the real
 * ones refuse: another author's note answers 403, an unseen link 404, an empty note 422. */
function stubServer(initial: LinkNote[], options: { listStatus?: number } = {}) {
  let notes = [...initial];
  const calls: Call[] = [];
  let next = 100;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    const reply = (status: number, json?: unknown) => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => json,
    });
    if (method === "GET") {
      if (options.listStatus) return reply(options.listStatus, { error: "link_not_found" });
      return reply(200, { notes });
    }
    if (method === "POST") {
      if (!String(body.body).trim()) {
        return reply(422, { error: "invalid_note", detail: "A note cannot be empty." });
      }
      const added = note(`n${next++}`, "analyst-1", body.body, 30, true);
      notes = [added, ...notes];
      return reply(201, added);
    }
    const id = url.split("/").pop();
    const target = notes.find((n) => n.id === id);
    if (!target) return reply(404, { error: "note_not_found" });
    if (!target.mine) {
      return reply(403, { error: "note_not_yours", detail: "Only the person who wrote a note can change or remove it." });
    }
    if (method === "PUT") {
      const edited = { ...target, body: body.body, edited_at: "2026-10-01T10:00:00Z" };
      notes = notes.map((n) => (n.id === id ? edited : n));
      return reply(200, edited);
    }
    notes = notes.filter((n) => n.id !== id);
    return reply(204);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function renderNotes(edgeId = "e1") {
  return render(
    <LinkNotes apiBaseUrl={BASE} bearerToken="tok" investigationId="inv-1" edgeId={edgeId} />,
  );
}

const mine = note("n1", "analyst-1", "Same address twice.", 5, true);
const theirs = note("n2", "analyst-2", "Seen by a colleague.", 10, false);

describe("LinkNotes", () => {
  beforeEach(() => undefined);

  it("lists the notes with who wrote them, newest first as the server gives them", async () => {
    stubServer([theirs, mine]);
    renderNotes();
    await screen.findByText("Seen by a colleague.");
    const items = screen.getAllByRole("listitem");
    expect(items[0]!.textContent).toContain("Seen by a colleague.");
    expect(items[0]!.textContent).toContain("analyst-2");
    expect(items[1]!.textContent).toContain("Same address twice.");
  });

  it("says so when the link has no notes", async () => {
    stubServer([]);
    renderNotes();
    expect(await screen.findByText("No notes on this link yet.")).toBeTruthy();
  });

  it("asks the server for this link's notes, with the bearer token", async () => {
    const { calls, fetchMock } = stubServer([]);
    renderNotes("e 1/x");
    await screen.findByText("No notes on this link yet.");
    expect(calls[0]!.url).toBe(`${BASE}/v1/investigations/inv-1/links/e%201%2Fx/notes`);
    expect((fetchMock.mock.calls[0]![1] as RequestInit).headers).toMatchObject({
      Authorization: "Bearer tok",
    });
  });

  it("says plainly who sees a note", async () => {
    stubServer([]);
    renderNotes();
    await screen.findByText("No notes on this link yet.");
    expect(document.body.textContent).toMatch(/everyone who can see this link/i);
  });

  it("keeps Add note off until there is something to add", async () => {
    stubServer([]);
    renderNotes();
    const add = (await screen.findByRole("button", { name: "Add note" })) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "   " } });
    expect(add.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Hello" } });
    expect(add.disabled).toBe(false);
  });

  it("adds a note, shows it at the top and empties the box", async () => {
    const { calls } = stubServer([theirs]);
    renderNotes();
    const box = (await screen.findByLabelText("New note")) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Check the lease." } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    await screen.findByText("Check the lease.");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ body: "Check the lease." });
    expect(screen.getAllByRole("listitem")[0]!.textContent).toContain("Check the lease.");
    expect(box.value).toBe("");
  });

  it("adds with Ctrl+Enter from the box", async () => {
    const { calls } = stubServer([]);
    renderNotes();
    const box = await screen.findByLabelText("New note");
    fireEvent.change(box, { target: { value: "By keyboard." } });
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    await screen.findByText("By keyboard.");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("keeps what was typed and says why when the server refuses it", async () => {
    stubServer([]);
    renderNotes();
    const box = (await screen.findByLabelText("New note")) as HTMLTextAreaElement;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 403,
        json: async () => ({ error: "insufficient_access" }),
      })),
    );
    fireEvent.change(box, { target: { value: "Will not save" } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/not be saved/i);
    expect(box.value).toBe("Will not save");
  });

  it("offers Edit and Delete on your own notes and on nobody else's", async () => {
    stubServer([theirs, mine]);
    renderNotes();
    await screen.findByText("Same address twice.");
    const [first, second] = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement];
    expect(within(first).queryByRole("button", { name: /edit/i })).toBeNull();
    expect(within(first).queryByRole("button", { name: /delete/i })).toBeNull();
    expect(within(second).getByRole("button", { name: /edit/i })).toBeTruthy();
    expect(within(second).getByRole("button", { name: /delete/i })).toBeTruthy();
  });

  it("edits your own note and marks it edited", async () => {
    const { calls } = stubServer([mine]);
    renderNotes();
    await screen.findByText("Same address twice.");
    fireEvent.click(screen.getByRole("button", { name: /edit note/i }));
    const box = screen.getByLabelText("Note text") as HTMLTextAreaElement;
    expect(box.value).toBe("Same address twice.");
    fireEvent.change(box, { target: { value: "Same address, three times." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Same address, three times.");
    expect(calls.find((c) => c.method === "PUT")?.url).toMatch(/\/notes\/n1$/);
    expect(document.body.textContent).toMatch(/edited/i);
    expect(screen.queryByLabelText("Note text")).toBeNull();
  });

  it("cancels an edit with Escape, changing nothing", async () => {
    const { calls } = stubServer([mine]);
    renderNotes();
    await screen.findByText("Same address twice.");
    fireEvent.click(screen.getByRole("button", { name: /edit note/i }));
    fireEvent.keyDown(screen.getByLabelText("Note text"), { key: "Escape" });
    expect(screen.queryByLabelText("Note text")).toBeNull();
    expect(screen.getByText("Same address twice.")).toBeTruthy();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("asks before deleting, and deletes only once confirmed", async () => {
    const { calls } = stubServer([mine]);
    renderNotes();
    await screen.findByText("Same address twice.");
    fireEvent.click(screen.getByRole("button", { name: /delete note/i }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(screen.queryByText("Same address twice.")).toBeNull());
    expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(1);
  });

  it("leaves the note alone when the delete is cancelled", async () => {
    const { calls } = stubServer([mine]);
    renderNotes();
    await screen.findByText("Same address twice.");
    fireEvent.click(screen.getByRole("button", { name: /delete note/i }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Same address twice.")).toBeTruthy();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  });

  it("says the link is out of view, and offers no box, when the server cannot find it", async () => {
    stubServer([], { listStatus: 404 });
    renderNotes();
    expect((await screen.findByRole("alert")).textContent).toMatch(/not in your view/i);
    expect(screen.queryByLabelText("New note")).toBeNull();
  });

  it("loads the new link's notes when another link is selected", async () => {
    const { calls } = stubServer([mine]);
    const { rerender } = renderNotes("e1");
    await screen.findByText("Same address twice.");
    rerender(
      <LinkNotes apiBaseUrl={BASE} bearerToken="tok" investigationId="inv-1" edgeId="e2" />,
    );
    await waitFor(() => expect(calls.filter((c) => c.method === "GET")).toHaveLength(2));
    expect(calls[1]?.url).toContain("/links/e2/notes");
  });

  it("shows a count once a note is getting near the limit", async () => {
    stubServer([]);
    renderNotes();
    const box = await screen.findByLabelText("New note");
    expect(screen.queryByText(/characters left/i)).toBeNull();
    fireEvent.change(box, { target: { value: "x".repeat(3800) } });
    expect(screen.getByText(/200 characters left/i)).toBeTruthy();
  });
});
