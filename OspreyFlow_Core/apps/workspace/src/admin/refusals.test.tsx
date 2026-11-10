// @vitest-environment jsdom
// ADR-145 Amendment 4 decision 12, as the owner ruled (c) (L2.7): an Admin action a person cannot take
// says why and which roles can, never only that it was refused, and never who holds the right
// (`whyNotByRole`). Red with the bare "does not hold the right" words back, or with the empty place
// saying nothing of who can.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { whyNotByRole } from "../help/roles";
import { AdminPlace } from "./AdminPlace";
import { Connections } from "./sections/Connections";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin's refusals say why and which roles can", () => {
  it("a right the Conduit asks for, by the roles that hold it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = new URL(String(url)).pathname;
        if (path === "/v1/admin/connections/c-api/test")
          return new Response(JSON.stringify({ detail: { error: "right_required", right: "administer_system" } }), { status: 403 });
        if (path === "/v1/admin/connections")
          return new Response(JSON.stringify([{ id: "c-api", kind: "api", name: "Telco", created_by: "a", created_at: "", datasets: [],
                                                 settings: { kind: "api", base_url: "https://t.example", auth: "none", pagination: "none" } }]), { status: 200 }); // prettier-ignore
        return new Response("[]", { status: 200 });
      }),
    );
    render(<Connections api={{ apiBaseUrl: "http://x", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Test connection: Telco" }));
    const said = await screen.findByRole("status");
    expect(said.textContent).toContain(whyNotByRole("administer_system"));
    expect(said.textContent).toContain("Administrator");
  });

  it("an account opening Admin with no administration right, by the role that has them", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["investigate"])} />);
    expect(screen.getByText(/Your account holds no administration right/).textContent).toContain(whyNotByRole("administer_system"));
  });
});
