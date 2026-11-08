// @vitest-environment jsdom
// ADR-144 decision 5 and Amendment 1: the cases, each once, with each case's views beneath it that
// this reader may see. A case's row opens the case; a view's row opens its case on that view.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseListing } from "./cases";
import { CaseList } from "./CaseList";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const at = "2026-10-14T16:40:00Z";
const CASES: CaseListing[] = [
  { id: "ledger", name: "Operation Ledger (synthetic demo)", level: "author", created_at: at, created_by: "a" },
  { id: "hmp", name: "HMP (synthetic demo)", level: "editor", created_at: at, created_by: "a" },
];
const SHARED = { id: "v1", case_id: "ledger", name: "Payments in March", created_by: "b", created_at: at, shared: true, chosen: 4 };
const MINE = { id: "v2", case_id: "ledger", name: "My working set", created_by: "a", created_at: at, shared: false, chosen: 2 };

/** The Conduit: the case list, and each case's views as this reader may see them (the ledger's two;
 * the HMP case's none). */
function serve() {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      asked.push(url);
      if (url.endsWith("/v1/investigations")) return new Response(JSON.stringify(CASES), { status: 200 });
      if (url.endsWith("/ledger/views")) return new Response(JSON.stringify([SHARED, MINE]), { status: 200 });
      if (url.endsWith("/hmp/views")) return new Response("[]", { status: 200 });
      return new Response("{}", { status: 404 });
    }),
  );
  return asked;
}

function mount(props: Partial<Parameters<typeof CaseList>[0]> = {}) {
  const onOpen = vi.fn();
  const onOpenView = vi.fn();
  render(<CaseList apiBaseUrl="http://t.invalid" bearerToken="tok" currentId="ledger" onOpen={onOpen} onOpenView={onOpenView} {...props} />);
  return { onOpen, onOpenView };
}

describe("CaseList", () => {
  it("lists each case once, marks the one you are in, and never a case beneath another", async () => {
    serve();
    mount();
    const list = await screen.findByRole("list", { name: "Cases" });
    const rows = Array.from(list.querySelectorAll(":scope > li"));
    expect(rows.map((r) => r.getAttribute("data-kind"))).toEqual(["case", "case"]);
    expect(within(list).getByRole("button", { name: "Operation Ledger (synthetic demo)" }).getAttribute("aria-current")).toBe("page");
    expect(within(list).getByText("you are here")).toBeTruthy();
  });

  it("lists each case's views beneath it, private or shared, and only the views the server gives", async () => {
    serve();
    mount();
    const views = await screen.findByRole("list", { name: "Views in Operation Ledger (synthetic demo)" });
    expect(within(views).getAllByRole("listitem").map((r) => r.textContent)).toEqual(["Payments in MarchShared", "My working setPrivate"]);
    expect(screen.queryByRole("list", { name: "Views in HMP (synthetic demo)" })).toBeNull();
  });

  it("opens a case from its row, and a case on a view from the view's row", async () => {
    serve();
    const { onOpen, onOpenView } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "HMP (synthetic demo)" }));
    expect(onOpen).toHaveBeenCalledWith("hmp");
    fireEvent.click(await screen.findByRole("button", { name: "Open the view Payments in March of Operation Ledger (synthetic demo)" }));
    expect(onOpenView).toHaveBeenCalledWith("ledger", SHARED);
  });

  it("in the case menu lists the cases without their views, and asks for none", async () => {
    const asked = serve();
    mount({ showViews: false });
    await screen.findByRole("list", { name: "Cases" });
    await waitFor(() => expect(asked).toContain("http://t.invalid/v1/investigations"));
    expect(asked.some((url) => url.includes("/views"))).toBe(false);
  });
});
