// @vitest-environment jsdom
// *Views ▾* by the graph (ADR-144 Amendment 3): the case's saved views as the Conduit lists them for this
// reader (the drawer's own read, `listViews`), each opened by the caller's `onOpen`.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { NO_VIEWS_YET, ViewsMenu } from "./ViewsMenu";

const API = "http://conduit";
const ALICES_PRIVATE = { id: "v-private", case_id: "c1", name: "Alice's own", created_by: "alice", created_at: "2026-11-08T10:00:00Z", shared: false, chosen: 3 };
const ALICES_SHARED = { id: "v-shared", case_id: "c1", name: "Payments in March", created_by: "alice", created_at: "2026-11-08T10:05:00Z", shared: true, chosen: 2 };

/** The Conduit as it answers each reader (the store's rule: a private view is its creator's alone), or
 * refusing the list outright. */
function conduit(answer: "alice" | "bob" | "none" | "refused") {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      asked.push(url);
      if (answer === "refused") return new Response(JSON.stringify({ error: "forbidden" }), { status: 403 });
      const listed = answer === "alice" ? [ALICES_PRIVATE, ALICES_SHARED] : answer === "bob" ? [ALICES_SHARED] : [];
      return new Response(JSON.stringify(listed), { status: 200 });
    }),
  );
  return asked;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function menu(extra: Partial<Parameters<typeof ViewsMenu>[0]> = {}) {
  const onOpen = vi.fn();
  render(<ViewsMenu apiBaseUrl={API} bearerToken="t" caseId="c1" onOpen={onOpen} {...extra} />);
  return { onOpen, button: screen.getByRole("button", { name: "Views" }) };
}

describe("ViewsMenu", () => {
  it("reads nothing until opened, then lists the views the Conduit sends this reader, and no other", async () => {
    const asked = conduit("bob");
    const { button } = menu();
    expect(asked).toEqual([]);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    const panel = await screen.findByRole("group", { name: "Saved views in this case" });
    await within(panel).findByRole("button", { name: /^Payments in March/ });
    expect(asked).toEqual([`${API}/v1/investigations/c1/views`]);
    expect(within(panel).getAllByRole("button").map((b) => b.textContent)).toEqual(["Payments in MarchShared"]);
    expect(screen.queryByText("Alice's own")).toBeNull();
  });

  it("opens the chosen view by the caller's onOpen and closes", async () => {
    conduit("alice");
    const { onOpen, button } = menu();
    fireEvent.click(button);
    fireEvent.click(await screen.findByRole("button", { name: /^Alice's own/ }));
    expect(onOpen).toHaveBeenCalledWith(ALICES_PRIVATE);
    expect(screen.queryByRole("group", { name: "Saved views in this case" })).toBeNull();
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("marks the view open now, and says which are private and which shared", async () => {
    conduit("alice");
    const { button } = menu({ openViewId: "v-shared" });
    fireEvent.click(button);
    const shared = await screen.findByRole("button", { name: /^Payments in March/ });
    expect(shared.getAttribute("aria-current")).toBe("true");
    expect(within(shared).getByText("Shared")).toBeTruthy();
    const own = screen.getByRole("button", { name: /^Alice's own/ });
    expect(own.getAttribute("aria-current")).toBeNull();
    expect(within(own).getByText("Private")).toBeTruthy();
  });

  it("says how to make one when the case has none", async () => {
    conduit("none");
    fireEvent.click(menu().button);
    expect(await screen.findByText(NO_VIEWS_YET)).toBeTruthy();
    expect(NO_VIEWS_YET).toBe("No saved views yet. Select nodes and choose Save as a view.");
  });

  it("says a refused list in words, not as an empty case", async () => {
    conduit("refused");
    fireEvent.click(menu().button);
    expect((await screen.findByRole("alert")).textContent).toBe("The views could not be loaded (403).");
    expect(screen.queryByText(NO_VIEWS_YET)).toBeNull();
  });

  it("reads the list again each time it opens, so a view saved since is there", async () => {
    const asked = conduit("bob");
    const { button } = menu();
    fireEvent.click(button);
    await screen.findByRole("button", { name: /^Payments in March/ });
    fireEvent.click(button);
    fireEvent.click(button);
    await screen.findByRole("button", { name: /^Payments in March/ });
    expect(asked).toHaveLength(2);
  });

  it("closes on Escape and gives focus back to its button", async () => {
    conduit("bob");
    const { button } = menu();
    fireEvent.click(button);
    const item = await screen.findByRole("button", { name: /^Payments in March/ });
    item.focus();
    fireEvent.keyDown(item, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Saved views in this case" })).toBeNull();
    expect(document.activeElement).toBe(button);
  });
});
