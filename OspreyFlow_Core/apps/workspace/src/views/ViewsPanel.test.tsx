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
    const list = await screen.findByRole("list", { name: "Saved views" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2); // the whole case, then the one shared view
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
    expect(screen.getByRole("button", { name: "Share with the case: Alice's own" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Share with the case: Kestrel's contacts" })).toBeNull();
    expect(screen.getByRole("button", { name: "Delete Alice's own" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete Kestrel's contacts" })).toBeTruthy();
    expect(screen.getAllByText("Private")).toHaveLength(1);
    expect(screen.getAllByText("Shared")).toHaveLength(1);
  });

  it("shares a private view through its own route and marks it shared", async () => {
    const calls = conduit("alice");
    panel("alice");
    fireEvent.click(await screen.findByRole("button", { name: "Share with the case: Alice's own" }));
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
    // The whole case first, open now with no saved view open (ADR-145 Amendment 17), then each view's own tag.
    expect(tags).toEqual(["Open now", "Private", "Shared"]);
    // ADR-145 Amendment 14 decision 1: a row's actions are GOV.UK links, as a summary list's are; the
    // question before a delete keeps GOV.UK's buttons.
    for (const name of ["Open Alice's own", "Share with the case: Alice's own", "Delete Alice's own"]) {
      expect(screen.getByRole("button", { name }).className).toContain("govuk-link");
      expect(screen.getByRole("button", { name }).className).not.toContain("govuk-button");
    }
    screen.getByRole("button", { name: "Delete Alice's own" }).click();
    expect((await screen.findByRole("button", { name: "Delete view" })).className).toContain("govuk-button--warning");
    expect(screen.getByRole("button", { name: "Cancel" }).className).toContain("govuk-button");
  });

  it("says a failed list as a failure, not as no views, and clears it when a later read succeeds", async () => {
    let fail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => (fail ? new Response("{}", { status: 500 }) : new Response(JSON.stringify([ALICES_SHARED]), { status: 200 }))),
    );
    const onOpen = vi.fn();
    const { rerender } = render(<ViewsPanel apiBaseUrl={API} bearerToken="t" caseId="c1" me="bob" onOpen={onOpen} refreshKey={0} />);
    expect((await screen.findByRole("alert")).textContent).toBe("The views could not be loaded (500).");
    expect(screen.queryByText(/No views yet/)).toBeNull();
    fail = false;
    rerender(<ViewsPanel apiBaseUrl={API} bearerToken="t" caseId="c1" me="bob" onOpen={onOpen} refreshKey={1} />);
    await screen.findByText("Kestrel's contacts");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says when the case has no views yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    panel("alice");
    expect(await screen.findByText(/No views yet/)).toBeTruthy();
  });

});

// ADR-145 Amendment 17 (the owner's exception, 14 November 2026): the panel the case line's *Saved views* opens.
// The list starts with the whole case, marked *Open now* while no saved view is open, and choosing it does what the
// strip's *Back to the whole case* does; the saved view open now is marked so and offers no *Open*; a view saved
// under the Glass's default name says, under it, its first item (as the Conduit names it for this reader) and when
// it was saved. In both looks.
const DEFAULT = { id: "v-default", case_id: "c1", name: "Selection of 3 nodes", created_by: "alice", created_at: "2026-11-14T12:01:00Z", shared: false, chosen: 3, first_item: "Tarbuck, Kyle" };
const DEFAULT_NONE_SEEN = { ...DEFAULT, id: "v-hidden", name: "Selection of 2 nodes", chosen: 2, first_item: null, created_at: "2026-11-14T11:40:00Z" };
const NAMED = { ...ALICES_SHARED, first_item: "Whitlow, Shona" };

function serving(listed: object[]) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(listed), { status: 200 })));
}

for (const look of ["standard", "govuk"] as const) {
  describe(`the saved views panel (${look})`, () => {
    const set = () => {
      if (look === "govuk") document.documentElement.setAttribute("data-brand", "govuk");
    };
    // The list by its name in either look: a summary list under GOV.UK, a list otherwise.
    const rows = () => screen.findByLabelText("Saved views");

    it("starts with the whole case, open now while no saved view is open, and offers it no Open", async () => {
      set();
      serving([DEFAULT, NAMED]);
      panel("alice", { onOpenWholeCase: vi.fn() });
      const list = await rows();
      const first = list.querySelector("[data-view-id]") as HTMLElement;
      expect(first.getAttribute("data-view-id")).toBe("whole-case");
      expect(within(first).getByText("The whole case")).toBeTruthy();
      expect(within(first).getByText("Open now")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Open the whole case" })).toBeNull();
    });

    it("offers the whole case while a saved view is open, and choosing it goes back to it", async () => {
      set();
      serving([DEFAULT, NAMED]);
      const onOpenWholeCase = vi.fn();
      panel("alice", { openViewId: "v-default", onOpenWholeCase });
      fireEvent.click(await screen.findByRole("button", { name: "Open the whole case" }));
      expect(onOpenWholeCase).toHaveBeenCalledTimes(1);
    });

    it("marks the saved view open now as Open now, and offers it no Open", async () => {
      set();
      serving([DEFAULT, NAMED]);
      panel("alice", { openViewId: "v-default", onOpenWholeCase: vi.fn() });
      const row = (await rows()).querySelector('[data-view-id="v-default"]') as HTMLElement;
      expect(within(row).getByText("Open now")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Open Selection of 3 nodes" })).toBeNull();
      expect(screen.getByRole("button", { name: "Open Kestrel's contacts" })).toBeTruthy();
      const whole = (await rows()).querySelector('[data-view-id="whole-case"]') as HTMLElement;
      expect(within(whole).queryByText("Open now")).toBeNull();
    });

    it("tells a view saved under the default name apart: its first item and when it was saved, under the name", async () => {
      set();
      serving([DEFAULT, DEFAULT_NONE_SEEN, NAMED]);
      panel("alice");
      const list = await rows();
      const seen = list.querySelector('[data-view-id="v-default"]') as HTMLElement;
      expect(within(seen).getByText("Tarbuck, Kyle · saved 14 Nov 2026, 12:01")).toBeTruthy();
      const none = list.querySelector('[data-view-id="v-hidden"]') as HTMLElement;
      expect(within(none).getByText("Saved 14 Nov 2026, 11:40")).toBeTruthy();
      // A view its creator named keeps its name alone: the second line is for the default name only.
      const named = list.querySelector(`[data-view-id="${NAMED.id}"]`) as HTMLElement;
      expect(within(named).queryByText(/Whitlow|saved/i)).toBeNull();
    });

    it("without the App's way back, the whole case is listed and offers no Open", async () => {
      set();
      serving([DEFAULT]);
      panel("alice", { openViewId: "v-default" });
      const whole = (await rows()).querySelector('[data-view-id="whole-case"]') as HTMLElement;
      expect(within(whole).getByText("The whole case")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Open the whole case" })).toBeNull();
    });
  });
}
