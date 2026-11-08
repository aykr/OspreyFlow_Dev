// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ViewsPanel } from "./ViewsPanel";

const API = "http://conduit";
const ALICES_PRIVATE = { id: "v-private", case_id: "c1", name: "Alice's own", created_by: "alice", created_at: "2026-11-08T10:00:00Z", shared: false, chosen: 3 };
const ALICES_SHARED = { id: "v-shared", case_id: "c1", name: "Kestrel's contacts", created_by: "alice", created_at: "2026-11-08T10:05:00Z", shared: true, chosen: 2 };

/** The Conduit as it answers each reader: Alice gets her private view and her shared one; Bob,
 * another member, gets only the shared one, because the store leaves the private one out. */
function conduit(reader: "alice" | "bob") {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      if (method === "GET") {
        const listed = reader === "alice" ? [ALICES_PRIVATE, ALICES_SHARED] : [ALICES_SHARED];
        return new Response(JSON.stringify(listed), { status: 200 });
      }
      if (method === "POST") return new Response(JSON.stringify({ ...ALICES_PRIVATE, shared: true }), { status: 200 });
      return new Response(null, { status: 204 });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-brand");
});

function panel(me: string, extra: Partial<Parameters<typeof ViewsPanel>[0]> = {}) {
  const onOpen = vi.fn();
  const onDeleted = vi.fn();
  render(<ViewsPanel apiBaseUrl={API} bearerToken={me} caseId="c1" me={me} onOpen={onOpen} onDeleted={onDeleted} {...extra} />);
  return { onOpen, onDeleted };
}

describe("ViewsPanel", () => {
  it("shows another member nothing of a private view, and no share or delete on a shared one", async () => {
    conduit("bob");
    panel("bob");
    const list = await screen.findByRole("list", { name: "Views in this case" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.queryByText("Alice's own")).toBeNull();
    expect(screen.getByText("Kestrel's contacts")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Kestrel's contacts" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Share / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Delete / })).toBeNull();
  });

  it("offers the creator Share on a private view, Delete on each, and says which is which", async () => {
    conduit("alice");
    panel("alice");
    await screen.findByText("Alice's own");
    expect(screen.getByRole("button", { name: "Share Alice's own with the case" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Share Kestrel's contacts with the case" })).toBeNull();
    expect(screen.getByRole("button", { name: "Delete Alice's own" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete Kestrel's contacts" })).toBeTruthy();
    expect(screen.getAllByText("Private")).toHaveLength(1);
    expect(screen.getAllByText("Shared")).toHaveLength(1);
  });

  it("shares a private view through its own route and marks it shared", async () => {
    const calls = conduit("alice");
    panel("alice");
    fireEvent.click(await screen.findByRole("button", { name: "Share Alice's own with the case" }));
    await waitFor(() => expect(screen.getAllByText("Shared")).toHaveLength(2));
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/v1/investigations/c1/views/v-private/share"))).toBe(true);
  });

  it("asks once before deleting, and deleting says nothing on the case goes with it", async () => {
    const calls = conduit("alice");
    const { onDeleted } = panel("alice");
    fireEvent.click(await screen.findByRole("button", { name: "Delete Alice's own" }));
    expect(screen.getByText("Delete this view? Nothing on the case is deleted with it.")).toBeTruthy();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Delete view" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("v-private"));
    expect(screen.queryByText("Alice's own")).toBeNull();
    expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/views/v-private"))).toBe(true);
  });

  it("opens a view from its row", async () => {
    conduit("bob");
    const { onOpen } = panel("bob");
    fireEvent.click(await screen.findByRole("button", { name: "Open Kestrel's contacts" }));
    expect(onOpen).toHaveBeenCalledWith(ALICES_SHARED);
  });

  it("is a GOV.UK summary list with Private and Shared tags under the GOV.UK brand", async () => {
    document.documentElement.setAttribute("data-brand", "govuk");
    conduit("alice");
    panel("alice");
    await screen.findByText("Alice's own");
    const list = document.querySelector("dl.govuk-summary-list");
    expect(list).not.toBeNull();
    const tags = Array.from(document.querySelectorAll("strong.govuk-tag")).map((t) => t.textContent);
    expect(tags).toEqual(["Private", "Shared"]);
    expect(screen.getByRole("button", { name: "Share Alice's own with the case" }).className).toContain("govuk-button");
  });

  it("says when the case has no views yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    panel("alice");
    expect(await screen.findByText(/No views yet/)).toBeTruthy();
  });
});
