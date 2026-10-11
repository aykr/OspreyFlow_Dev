// @vitest-environment jsdom
// ADR-052 §9, the Share panel. The Conduit enforces every level; these prove the Glass asks for
// what the Author chose, shows people by name where the Conduit gave one, offers the controls only
// to an Author, never offers to remove the last Author, and stays out of the way of an account that
// may not share cases at all.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseAccessPanel } from "./CaseAccessPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function serve(access: () => Response, change: (key: string, body: unknown) => Response = () => new Response(null, { status: 204 })) {
  const calls: { key: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      return key === "GET /v1/investigations/c1/access" ? access() : change(key, body);
    }),
  );
  return calls;
}

const AUTHOR_VIEW = {
  your_level: "author",
  unit_level: null,
  grants: { alice: "author", "dash-1": "viewer" },
  names: { alice: "Alice Author" },
};

const panel = () => render(<CaseAccessPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);

describe("who can open a case", () => {
  it("shows the Author everyone with access, by name where there is one and by id where not", async () => {
    serve(() => json(200, AUTHOR_VIEW));
    panel();
    const list = await screen.findByRole("list", { name: "Accounts with access" });
    expect(list.textContent).toContain("Alice Author");
    expect(list.textContent).toContain("alice");
    expect(list.textContent).toContain("dash-1");
    expect(screen.getByText("You are its Author.")).toBeTruthy();
  });

  it("gives the account typed the level chosen, and reads the list again", async () => {
    const calls = serve(() => json(200, AUTHOR_VIEW));
    panel();
    fireEvent.change(await screen.findByLabelText("Account id"), { target: { value: "  13942885-a6b1  " } });
    fireEvent.change(screen.getByLabelText("Level"), { target: { value: "viewer" } });
    fireEvent.click(screen.getByRole("button", { name: "Give access" }));
    await waitFor(() => expect(calls.filter((c) => c.key.startsWith("GET")).length).toBe(2));
    const put = calls.find((c) => c.key.startsWith("PUT"))!;
    expect(put.key).toBe("PUT /v1/investigations/c1/access/grants/13942885-a6b1");
    expect(put.body).toEqual({ level: "viewer" });
  });

  it("removes an account's access", async () => {
    const calls = serve(() => json(200, AUTHOR_VIEW));
    panel();
    fireEvent.click(await screen.findByRole("button", { name: "Remove dash-1's access" }));
    await waitFor(() => expect(calls.some((c) => c.key === "DELETE /v1/investigations/c1/access/grants/dash-1")).toBe(true));
  });

  it("never offers to remove the last Author, and offers it once there are two", async () => {
    serve(() => json(200, AUTHOR_VIEW));
    panel();
    await screen.findByRole("list", { name: "Accounts with access" });
    expect(screen.queryByRole("button", { name: "Remove Alice Author's access" })).toBeNull();
    cleanup();
    serve(() => json(200, { ...AUTHOR_VIEW, grants: { alice: "author", bob: "author" } }));
    panel();
    expect(await screen.findByRole("button", { name: "Remove Alice Author's access" })).toBeTruthy();
  });

  it("shows a Viewer only their own level, with nothing to change", async () => {
    serve(() => json(200, { your_level: "viewer", unit_level: null, grants: null, names: null }));
    panel();
    expect(await screen.findByText("You are its Viewer.")).toBeTruthy();
    expect(screen.queryByLabelText("Account id")).toBeNull();
    expect(screen.queryByRole("list", { name: "Accounts with access" })).toBeNull();
  });

  it("is not shown at all to an account that may not share cases", async () => {
    const calls = serve(() => json(403, { detail: "share_case is needed" }));
    panel();
    await waitFor(() => expect(calls.length).toBe(1));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Who can open this case" })).toBeNull());
  });

  it("says a refusal in words", async () => {
    serve(
      () => json(200, AUTHOR_VIEW),
      () => json(403, {}),
    );
    panel();
    fireEvent.change(await screen.findByLabelText("Account id"), { target: { value: "bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Give access" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Only the case's Author can change who can open it.");
  });
});
