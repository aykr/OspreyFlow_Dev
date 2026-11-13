// @vitest-environment jsdom
// ADR-148 Amendment 10: Admin › Dashboards on Entra ID sign-in. A dashboard identity is its own Entra
// app registration, which holds its secret: Dashboards asks for its application id, sends it, shows no
// secret, and says which app role the registration needs. Keycloak's form is unchanged (the control).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dashboards } from "./Dashboards";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const APP = "dddddddd-eeee-4fff-8000-111111111111";

function serve(kind: "entra" | "keycloak") {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (path === "dashboards/sign-in") return json(200, { kind });
      if (path === "/v1/handling-scheme") return json(200, { classification: ["OFFICIAL"] });
      if (path === "dashboards" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { application_id?: string };
        const id = body.application_id ?? "osprey-dashboard-board";
        return json(201, {
          dashboard: { client_id: id, account_id: id, clearance: "OFFICIAL", org_unit: "unit-2", receivable_handling_codes: ["P"] },
          secret: kind === "entra" ? null : "s3cret",
        });
      }
      if (path === "dashboards") return json(200, []);
      return json(200, {});
    }),
  );
  return sent;
}

const fill = async (applicationId?: string) => {
  render(<Dashboards api={{ apiBaseUrl: "http://x", bearerToken: "t" }} />);
  fireEvent.change(await screen.findByLabelText("Dashboard name"), { target: { value: "Board" } });
  fireEvent.change(screen.getByLabelText("Dashboard unit"), { target: { value: "unit-2" } });
  await waitFor(() => expect((screen.getByLabelText("Dashboard reads at clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
  if (applicationId !== undefined) {
    fireEvent.change(await screen.findByLabelText("Dashboard application id"), { target: { value: applicationId } });
  }
};

describe("Admin › Dashboards on Entra ID sign-in", () => {
  it("registers by application id, shows no secret, and names the app role to grant", async () => {
    const sent = serve("entra");
    await fill();
    const register = screen.getByRole("button", { name: "Register" });
    expect((register as HTMLButtonElement).disabled).toBe(true); // no application id yet
    fireEvent.change(screen.getByLabelText("Dashboard application id"), { target: { value: APP } });
    fireEvent.click(register);
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain(`${APP} is registered`);
    expect(status.textContent).toContain("Dashboard.Read");
    expect(status.textContent).not.toContain("shown once");
    const posted = sent.find((s) => s.path === "POST dashboards");
    expect(posted?.body).toMatchObject({ name: "Board", clearance: "OFFICIAL", org_unit: "unit-2", application_id: APP });
  });

  it("on Keycloak asks for no application id and shows the secret once, as before", async () => {
    const sent = serve("keycloak");
    await fill();
    expect(screen.queryByLabelText("Dashboard application id")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect((await screen.findByRole("status")).textContent).toContain("shown once");
    expect(sent.find((s) => s.path === "POST dashboards")?.body).not.toHaveProperty("application_id");
  });
});
