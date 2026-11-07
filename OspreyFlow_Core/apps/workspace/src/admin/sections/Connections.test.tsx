// @vitest-environment jsdom
// ADR-140 Amendment 4: the Admin area's Connections. Red if the tab shows to someone without
// administer_system, or a connection named here never reaches the route.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "../AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FILES = { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" };

describe("Connections", () => {
  it("is a tab for administer_system alone, lists the built-in Files, and names a new one", async () => {
    const posts: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = new URL(String(url)).pathname;
        if (path === "/v1/admin/connections" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { ok: true, status: 201, json: async () => ({ ...FILES, id: "c2", name: "Second folder", created_by: "adm-1" }) } as Response;
        }
        if (path === "/v1/admin/connections") return { ok: true, status: 200, json: async () => [FILES] } as Response;
        return { ok: true, status: 200, json: async () => [] } as Response;
      }),
    );
    render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(["operate_schedules"])} />);
    expect(screen.queryByRole("button", { name: "Connections" })).toBeNull();
    cleanup();
    render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(["administer_system"])} />);
    fireEvent.click(screen.getByRole("button", { name: "Connections" }));
    expect(await screen.findByText("Files: the ingest root")).toBeTruthy();
    expect(screen.getByText("built in")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "New Files connection" }), { target: { value: "Second folder" } });
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    await waitFor(() => expect(posts).toEqual([{ kind: "files", name: "Second folder" }]));
    expect(await screen.findByText("Named Second folder.")).toBeTruthy();
  });
});
