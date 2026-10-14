// @vitest-environment jsdom
// ADR-084 Amendment 4 (the owner, 14 October 2026: "the current display method for the Branch and main
// case is very confusing, i need a method to delete a branch as through the Glass view"): one tree of
// cases, each branch beneath its case, opened, renamed or deleted from its own row.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseListing } from "./cases";
import { CaseTree } from "./CaseTree";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const at = "2026-10-14T16:40:00Z";
const CASES: CaseListing[] = [
  { id: "ledger", name: "Operation Ledger (synthetic demo)", level: "author", created_at: at, created_by: "a" },
  { id: "b-small", name: "Branch of Operation Ledger (synthetic demo) (2 nodes)", level: "author", created_at: at, created_by: "a", branched_from: "ledger" },
  { id: "b-shared", name: "Branch of Operation Ledger (synthetic demo) (37 nodes)", level: "viewer", created_at: "2026-10-13T09:12:00Z", created_by: "b", branched_from: "ledger" },
  { id: "hmp", name: "HMP (synthetic demo)", level: "editor", created_at: at, created_by: "a" },
];

function serve(cases: CaseListing[] = CASES) {
  const sent: { method: string; url: string; body?: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    sent.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (method === "GET") return new Response(JSON.stringify(cases), { status: 200 });
    return new Response(null, { status: method === "DELETE" ? 204 : 200 });
  }));
  return sent;
}

function mount(currentId: string, onOpen = vi.fn(), isAdministrator = false) {
  render(<CaseTree apiBaseUrl="http://t.invalid" bearerToken="tok" currentId={currentId} onOpen={onOpen} isAdministrator={isAdministrator} />);
  return onOpen;
}

describe("CaseTree", () => {
  it("shows each case with its branches beneath it, named by size and time, and where you are", async () => {
    serve();
    mount("b-small");
    const tree = await screen.findByRole("list", { name: "Cases and their branches" });
    const rows = within(tree).getAllByRole("listitem").map((li) => li.getAttribute("data-kind") + ":" + li.querySelector(".case-tree__name")?.textContent);
    expect(rows).toEqual([
      "case:Operation Ledger (synthetic demo)",
      "branch:⑂ 37 nodes · 13 Oct 09:12",
      "branch:⑂ 2 nodes · 14 Oct 16:40",
      "case:HMP (synthetic demo)",
    ]);
    expect(screen.getByRole("button", { name: "2 nodes · 14 Oct 16:40" }).getAttribute("aria-current")).toBe("page");
  });

  it("opens a branch from its row", async () => {
    serve();
    const onOpen = mount("ledger");
    fireEvent.click(await screen.findByRole("button", { name: "37 nodes · 13 Oct 09:12" }));
    expect(onOpen).toHaveBeenCalledWith("b-shared");
  });

  it("deletes a branch after asking once, in place, and it leaves the tree", async () => {
    const sent = serve();
    mount("ledger");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByText(/Delete this branch\? It leaves every list for everyone/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete branch" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "2 nodes · 14 Oct 16:40" })).toBeNull());
    expect(sent.find((s) => s.method === "DELETE")?.url).toBe("http://t.invalid/v1/investigations/b-small");
  });

  it("deleting the branch you are in takes you back to the case it came from", async () => {
    serve();
    const onOpen = mount("b-small");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete branch" }));
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith("ledger"));
  });

  it("renames a branch from its row, and shows the new name", async () => {
    const sent = serve();
    mount("ledger");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }));
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    const field = screen.getByRole("textbox", { name: "Branch name" });
    fireEvent.change(field, { target: { value: "Midland Pallets route" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(await screen.findByRole("button", { name: "Midland Pallets route" })).toBeTruthy();
    expect(sent.find((s) => s.method === "PATCH")?.body).toEqual({ name: "Midland Pallets route" });
  });

  it("offers Rename and Delete only to the branch's Author; an administrator may delete", async () => {
    serve();
    mount("ledger");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 37 nodes · 13 Oct 09:12" }));
    expect(screen.queryByRole("button", { name: "Rename" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    cleanup();
    serve();
    mount("ledger", vi.fn(), true);
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 37 nodes · 13 Oct 09:12" }));
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });

  it("says a refusal in words and keeps the branch", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) =>
      (init?.method ?? "GET") === "GET" ? new Response(JSON.stringify(CASES), { status: 200 }) : new Response(null, { status: 403 }),
    ));
    mount("ledger");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete branch" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "You do not have permission to remove this case.");
    expect(screen.getByRole("button", { name: "2 nodes · 14 Oct 16:40" })).toBeTruthy();
  });
});
