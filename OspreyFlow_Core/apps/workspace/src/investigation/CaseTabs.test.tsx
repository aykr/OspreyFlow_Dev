// @vitest-environment jsdom
//
// The strip of tabs above the workspace (ADR-084). A tab is a saved branch of the case on screen.
// It enforces nothing: the Conduit decides who may see, open or discard a case, and these prove the
// strip asks the right routes and shows what the answers say.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CaseTabs } from "./CaseTabs";

const fetchMock = vi.fn();

type Row = {
  id: string;
  name: string;
  level: "viewer" | "editor" | "author";
  created_at: string;
  created_by: string;
  branched_from: string | null;
  tab_hidden?: boolean;
};

function row(id: string, branchedFrom: string | null, at: string, extra: Partial<Row> = {}): Row {
  return { id, name: id, level: "author", created_at: at, created_by: "a", branched_from: branchedFrom, ...extra };
}

const FAMILY: Row[] = [
  row("Fixture", null, "2026-10-01T00:00:00Z"),
  row("Volkovs", "Fixture", "2026-10-02T00:00:00Z"),
  row("Bank staff", "Fixture", "2026-10-03T00:00:00Z", { tab_hidden: true }),
];

function serve(rows: Row[]): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (!init || !init.method) return { ok: true, status: 200, json: async () => rows };
    return { ok: true, status: init.method === "DELETE" || init.method === "PUT" ? 204 : 200, json: async () => ({}) };
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function setup(currentId = "Fixture", overrides: Partial<Parameters<typeof CaseTabs>[0]> = {}) {
  const onOpen = vi.fn();
  render(
    <CaseTabs apiBaseUrl="http://api" bearerToken="tok" currentId={currentId} onOpen={onOpen} {...overrides} />,
  );
  return { onOpen };
}

const tabs = () => within(screen.getByRole("navigation", { name: "Case tabs" }));

describe("CaseTabs", () => {
  it("shows nothing for a case that has never been branched", async () => {
    serve([row("Fixture", null, "2026-10-01T00:00:00Z")]);
    setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("navigation", { name: "Case tabs" })).toBeNull();
  });

  it("shows the original case first and its open branches after it, and marks the one on screen", async () => {
    serve(FAMILY);
    setup("Volkovs");
    await screen.findByRole("navigation", { name: "Case tabs" });
    const names = tabs()
      .getAllByRole("button", { name: /^(Fixture|Volkovs|Bank staff)$/ })
      .map((b) => b.textContent);
    expect(names).toEqual(["Fixture", "Volkovs"]);
    expect(tabs().getByRole("button", { name: "Volkovs" }).getAttribute("aria-current")).toBe("page");
    expect(tabs().getByRole("button", { name: "Fixture" }).getAttribute("aria-current")).toBeNull();
  });

  it("opens a tab when it is pressed", async () => {
    serve(FAMILY);
    const { onOpen } = setup("Fixture");
    fireEvent.click(await tabs_when_ready("Volkovs"));
    expect(onOpen).toHaveBeenCalledWith("Volkovs");
  });

  it("does not offer to close the original case", async () => {
    serve(FAMILY);
    setup("Fixture");
    await screen.findByRole("navigation", { name: "Case tabs" });
    expect(tabs().queryByRole("button", { name: "Close tab Fixture" })).toBeNull();
    expect(tabs().getByRole("button", { name: "Close tab Volkovs" })).toBeTruthy();
  });

  it("closing a tab asks the tab route, takes it from the strip and keeps it in the Branches list", async () => {
    serve(FAMILY);
    setup("Fixture");
    fireEvent.click(await screen.findByRole("button", { name: "Close tab Volkovs" }));
    await waitFor(() => expect(tabs().queryByRole("button", { name: "Volkovs" })).toBeNull());
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT") as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations/Volkovs/tab");
    expect(JSON.parse(init.body as string)).toEqual({ hidden: true });
    fireEvent.click(screen.getByRole("button", { name: /Branches/ }));
    expect(within(screen.getByRole("group", { name: "Branches" })).getByText("Volkovs")).toBeTruthy();
  });

  it("does not take the tab away when the server refuses", async () => {
    serve(FAMILY);
    setup("Fixture");
    await screen.findByRole("button", { name: "Close tab Volkovs" });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
      init?.method === "PUT"
        ? { ok: false, status: 500, json: async () => ({}) }
        : { ok: true, status: 200, json: async () => FAMILY },
    );
    fireEvent.click(screen.getByRole("button", { name: "Close tab Volkovs" }));
    await screen.findByRole("alert");
    expect(tabs().getByRole("button", { name: "Volkovs" })).toBeTruthy();
  });

  it("lists every branch in the Branches menu with its state, and says how many are open", async () => {
    serve(FAMILY);
    setup("Fixture");
    const menu = await screen.findByRole("button", { name: /Branches \(1 open of 2\)/ });
    fireEvent.click(menu);
    const panel = screen.getByRole("group", { name: "Branches" });
    expect(within(panel).getByText("Volkovs").closest("li")?.textContent).toMatch(/open/i);
    expect(within(panel).getByText("Bank staff").closest("li")?.textContent).toMatch(/hidden/i);
  });

  it("brings a hidden tab back from the Branches menu", async () => {
    serve(FAMILY);
    setup("Fixture");
    fireEvent.click(await screen.findByRole("button", { name: /Branches/ }));
    fireEvent.click(screen.getByRole("button", { name: "Show tab Bank staff" }));
    await waitFor(() => expect(tabs().getByRole("button", { name: "Bank staff" })).toBeTruthy());
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT") as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ hidden: false });
  });

  it("keeps the case on screen in the strip even if its tab was closed", async () => {
    serve(FAMILY);
    setup("Bank staff");
    await screen.findByRole("navigation", { name: "Case tabs" });
    expect(tabs().getByRole("button", { name: "Bank staff" }).getAttribute("aria-current")).toBe("page");
  });

  it("discards only after a confirmation that says nothing is deleted, then drops the branch from the list", async () => {
    serve(FAMILY);
    setup("Fixture");
    fireEvent.click(await screen.findByRole("button", { name: /Branches/ }));
    fireEvent.click(screen.getByRole("button", { name: "Discard Volkovs" }));
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(false);
    expect(screen.getByText(/nothing is deleted/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm discard" }));
    await waitFor(() => expect(tabs().queryByRole("button", { name: "Volkovs" })).toBeNull());
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "DELETE") as [string, RequestInit];
    expect(url).toBe("http://api/v1/investigations/Volkovs");
    expect(init.method).toBe("DELETE");
  });

  it("offers no discard to an account that is only a Viewer of the branch", async () => {
    serve([
      row("Fixture", null, "2026-10-01T00:00:00Z"),
      row("Volkovs", "Fixture", "2026-10-02T00:00:00Z", { level: "viewer" }),
    ]);
    setup("Fixture");
    fireEvent.click(await screen.findByRole("button", { name: /Branches/ }));
    expect(screen.queryByRole("button", { name: "Discard Volkovs" })).toBeNull();
  });

  it("offers a discard to an administrator of the unit whatever their level", async () => {
    serve([
      row("Fixture", null, "2026-10-01T00:00:00Z"),
      row("Volkovs", "Fixture", "2026-10-02T00:00:00Z", { level: "viewer" }),
    ]);
    setup("Fixture", { isAdministrator: true });
    fireEvent.click(await screen.findByRole("button", { name: /Branches/ }));
    expect(screen.getByRole("button", { name: "Discard Volkovs" })).toBeTruthy();
  });

  it("does not offer to discard the branch that is on screen", async () => {
    serve(FAMILY);
    setup("Volkovs");
    fireEvent.click(await screen.findByRole("button", { name: /Branches/ }));
    expect(screen.queryByRole("button", { name: "Discard Volkovs" })).toBeNull();
    expect(screen.getByRole("button", { name: "Discard Bank staff" })).toBeTruthy();
  });
});

async function tabs_when_ready(name: string): Promise<HTMLElement> {
  await screen.findByRole("navigation", { name: "Case tabs" });
  return within(screen.getByRole("navigation", { name: "Case tabs" })).getByRole("button", { name });
}
