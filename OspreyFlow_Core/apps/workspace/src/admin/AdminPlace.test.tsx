// @vitest-environment jsdom
// ADR-110 Amendment 1, ADR-112: the Admin area. Tabs follow the account's rights; a person's roles are
// saved whole with their other grants kept; a dashboard's secret is shown once; a refusal is said.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace, feedFreshness } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const PERSON = { id: "u1", username: "osprey-demo-analyst", name: "Demo Analyst", enabled: true,
                 roles: ["analyst", "right:read_export_ledger"], clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore

function serve(handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "people") return json(200, [PERSON]);
      if (path === "people/u1/roles") return json(200, { ...PERSON, roles: (JSON.parse(String(init?.body)) as { roles: string[] }).roles });
      if (path === "dashboards" && init?.method === "POST")
        return json(201, { dashboard: { client_id: "osprey-dashboard-board", account_id: "sa-1", clearance: "OFFICIAL", org_unit: "verify" }, secret: "s3cret" });
      if (path === "dashboards") return json(200, []);
      if (path === "/v1/handling-scheme")
        return json(200, { classification: ["OFFICIAL", "SECRET"], handling_codes: { P: {}, C: {} } });
      if (path === "system") return json(200, { version: "1.2", components: [{ name: "Graph store", ok: false, millis: 5000, detail: "unreachable" }] });
      return json(404, {});
    }),
  );
  return sent;
}

function place(rights: string[]) {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
}

describe("the Admin area", () => {
  it("shows only the tabs the account holds a right for", async () => {
    serve();
    place(["administer_system"]);
    expect(screen.queryByRole("tab", { name: "People and roles" })).toBeNull();
    expect(await screen.findByText("not answering: unreachable")).toBeTruthy();
  });

  it("saves a person's roles whole, keeping their other grants", async () => {
    const sent = serve();
    place(["manage_people"]);
    fireEvent.click(await screen.findByLabelText("Reports Viewer for osprey-demo-analyst"));
    fireEvent.click(screen.getByRole("button", { name: "Save roles for osprey-demo-analyst" }));
    await waitFor(() => expect(sent.some((s) => s.path === "PUT people/u1/roles")).toBe(true));
    expect(sent.find((s) => s.path === "PUT people/u1/roles")?.body).toEqual({
      roles: ["analyst", "reports_viewer", "right:read_export_ledger"],
    });
    expect(await screen.findByText(/Saved\./)).toBeTruthy();
  });

  it("registers a dashboard and shows its secret once", async () => {
    serve();
    place(["manage_dashboards"]);
    fireEvent.change(await screen.findByLabelText("Dashboard name"), { target: { value: "Board" } });
    fireEvent.change(screen.getByLabelText("Dashboard unit"), { target: { value: "verify" } });
    await waitFor(() => expect((screen.getByLabelText("Dashboard clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("s3cret")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Dashboard identities" }).textContent).toContain("sa-1");
  });

  it("says why a dashboard above one's clearance is refused", async () => {
    serve((path, init) =>
      path === "dashboards" && init?.method === "POST"
        ? json(403, { detail: { error: "dashboard_above_your_clearance", clearance: "SECRET" } })
        : null,
    );
    place(["manage_dashboards"]);
    fireEvent.change(await screen.findByLabelText("Dashboard name"), { target: { value: "Board" } });
    fireEvent.change(screen.getByLabelText("Dashboard unit"), { target: { value: "verify" } });
    await waitFor(() => expect((screen.getByLabelText("Dashboard clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("A dashboard cannot read above your own clearance (SECRET asked).")).toBeTruthy();
  });
});

describe("how fresh a dashboard's figures are", () => {
  const base = { client_id: "osprey-dashboard-board", account_id: "sa-1" };

  it("says a standing failure first, in the sync service's words, with the last good pull", () => {
    const shown = feedFreshness({ ...base, last_pulled: "2026-10-11T10:24:32Z", last_failure: "the feed was refused (403)",
                                  failed_at: "2026-10-11T10:39:00Z", cases_pulled: 1 });  // prettier-ignore
    expect(shown).toEqual({
      text: "Failing since 2026-10-11 10:39 UTC: the feed was refused (403); last good pull 2026-10-11 10:24 UTC",
      failing: true,
    });
  });

  it("says when it last pulled, and how many cases", () => {
    expect(feedFreshness({ ...base, last_pulled: "2026-10-11T10:24:32Z", cases_pulled: 2 })).toEqual({
      text: "Pulled 2026-10-11 10:24 UTC · 2 cases",
      failing: false,
    });
  });

  it("says a dashboard never pulled has been given no case", () => {
    expect(feedFreshness(base).text).toBe("Never pulled: no case has given it Viewer yet");
  });
});


// ADR-114 Amendment 5 (B4c): invite a person, edit their access, disable, enable, reset sign-in.
const CODE = "ABCD-EFGH-JKLM-NPQR";
const invited = (delivery: "email" | "one_time_code") =>
  json(201, {
    person: { id: "u2", username: "new.person", name: "New Person", enabled: true, roles: ["analyst"],
              clearance: "OFFICIAL", org_unit: "verify", email: "new@example.org", receivable_handling_codes: ["P"],
              must_set_password: true },  // prettier-ignore
    delivery,
    one_time_code: delivery === "one_time_code" ? CODE : null,
  });

function invite() {
  fireEvent.change(screen.getByLabelText("Sign-in name"), { target: { value: "new.person" } });
  fireEvent.change(screen.getByLabelText("First name"), { target: { value: "New" } });
  fireEvent.change(screen.getByLabelText("Last name"), { target: { value: "Person" } });
  fireEvent.change(screen.getByLabelText("Email (optional)"), { target: { value: "new@example.org" } });
  fireEvent.change(screen.getByLabelText("Invite unit"), { target: { value: "verify" } });
  fireEvent.click(screen.getByLabelText("Invite with handling code P"));
  fireEvent.click(screen.getByLabelText("Invite as Analyst"));
  fireEvent.click(screen.getByRole("button", { name: "Invite" }));
}

describe("people: invite, access, disable, enable, reset sign-in", () => {
  it("invites a person and hands over their one-time code once, with what to do with it", async () => {
    const sent = serve((path, init) => (path === "people" && init?.method === "POST" ? invited("one_time_code") : null));
    place(["manage_people"]);
    await screen.findByText("Demo Analyst");
    await waitFor(() => expect((screen.getByLabelText("Invite clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    invite();
    expect(await screen.findByText(CODE)).toBeTruthy();
    expect(screen.getByText(/Give this one-time code to New Person in person/)).toBeTruthy();
    const posted = sent.find((s) => s.path === "POST people")!.body;
    expect(posted).toEqual({ username: "new.person", first_name: "New", last_name: "Person", email: "new@example.org",
                             clearance: "OFFICIAL", org_unit: "verify", receivable_handling_codes: ["P"], roles: ["analyst"] });  // prettier-ignore
    expect(screen.getByText(/must set a password/)).toBeTruthy();
  });

  it("says an emailed invitation went out, and shows no code", async () => {
    serve((path, init) => (path === "people" && init?.method === "POST" ? invited("email") : null));
    place(["manage_people"]);
    await screen.findByText("Demo Analyst");
    invite();
    expect(await screen.findByText(/An email with a link to set a password went to new@example.org/)).toBeTruthy();
    expect(screen.queryByText(CODE)).toBeNull();
  });

  it("disables a person only once it is confirmed, and enables them again", async () => {
    const sent = serve((path) => {
      if (path === "people/u1/disable") return json(200, { ...PERSON, enabled: false });
      if (path === "people/u1/enable") return json(200, { ...PERSON, enabled: true });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable osprey-demo-analyst" }));
    expect(sent.some((s) => s.path === "POST people/u1/disable")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Confirm disabling osprey-demo-analyst" }));
    expect(await screen.findByText("Disabled")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Enable osprey-demo-analyst" }));
    await waitFor(() => expect(sent.some((s) => s.path === "POST people/u1/enable")).toBe(true));
    await waitFor(() => expect(screen.queryByText("Disabled")).toBeNull());
  });

  it("resets a person's sign-in and hands over the new code", async () => {
    serve((path) =>
      path === "people/u1/reset-sign-in"
        ? json(200, { person: { ...PERSON, must_set_password: true }, delivery: "one_time_code", one_time_code: CODE })
        : null,
    );
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Reset sign-in for osprey-demo-analyst" }));
    expect(await screen.findByText(CODE)).toBeTruthy();
  });

  it("edits a person's access, and says a refusal above your own clearance in words", async () => {
    const sent = serve((path, init) => {
      if (path !== "people/u1/access") return null;
      const body = JSON.parse(String(init?.body)) as { clearance: string };
      return body.clearance === "SECRET"
        ? json(403, { detail: { error: "above_your_clearance", clearance: "SECRET" } })
        : json(200, { ...PERSON, ...body });
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Edit access for osprey-demo-analyst" }));
    await waitFor(() => expect((screen.getByLabelText("Clearance for osprey-demo-analyst") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.change(screen.getByLabelText("Clearance for osprey-demo-analyst"), { target: { value: "SECRET" } });
    fireEvent.click(screen.getByRole("button", { name: "Save access for osprey-demo-analyst" }));
    expect(await screen.findByText("You cannot give a clearance above your own (SECRET asked).")).toBeTruthy();
    expect(sent.find((s) => s.path === "PUT people/u1/access")!.body).toEqual({
      clearance: "SECRET", org_unit: "verify", receivable_handling_codes: [],
    });
  });
});
