// @vitest-environment jsdom
// ADR-110 Amendment 1, ADR-112: the Admin area. Its sections follow the account's rights (ADR-145 decision 5); a person's roles are
// saved whole with their other grants kept; a dashboard's secret is shown once; a refusal is said.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace, feedFreshness } from "./AdminPlace";
import { convertedWords } from "./sections/System";

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
      if (path === "organisation-arrivals") return json(200, []);
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

/** The Admin place for these rights, and (ADR-145 decision 5) the section opened from its side list. */
function place(rights: string[], section?: string) {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
  if (section) fireEvent.click(within(screen.getByRole("navigation", { name: "Admin sections" })).getByRole("button", { name: section }));
}

describe("the Admin area", () => {
  it("shows only the sections the account holds a right for", async () => {
    serve();
    place(["administer_system"], "System");
    expect(screen.queryByRole("button", { name: "People and roles" })).toBeNull();
    expect(await screen.findByText("not answering: unreachable")).toBeTruthy();
  });

  // ADR-114 Amendment 36 (build order step 28 (d)): a part that answered and is wrong says what to do.
  it("says when the Conduit cannot act for people, and what to run, in place of 'not answering'", async () => {
    serve((path) =>
      path === "system"
        ? json(200, {
            version: "1.2",
            components: [
              { name: "Identity provider", ok: true, millis: 12, detail: null, notice: null },
              { name: "Acting for people", ok: false, millis: 12, detail: "the identity provider refused the Conduit's credentials",
                notice: "The Conduit cannot act for people: run `ospreyflow repair-sign-in`" },
            ],
          })
        : null,
    );
    place(["administer_system"], "System");
    const line = await screen.findByText("The Conduit cannot act for people: run `ospreyflow repair-sign-in`");
    expect(line).toBeTruthy();
    expect(screen.queryByText(/not answering/)).toBeNull();
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
    await waitFor(() => expect((screen.getByLabelText("Dashboard reads at clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
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
    await waitFor(() => expect((screen.getByLabelText("Dashboard reads at clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("A dashboard cannot read above your own clearance (SECRET asked).")).toBeTruthy();
  });
});

// ADR-090 Amendment 4 (as Amendment 5 timed it, L2.7): proposed types are decided on the Studio's Model
// tab of their dataset, so Admin has no Proposed types section, for a holder of manage_ontology or any
// other right, and nothing in Admin asks for the proposals.
describe("Proposed types are not in the Admin area", () => {
  it("is no section, even for a holder of manage_ontology with every other right", () => {
    const sent = serve();
    place(["manage_ontology", "manage_people", "manage_dashboards", "administer_system", "operate_schedules", "read_audit"]);
    const nav = screen.getByRole("navigation", { name: "Admin sections" });
    expect(within(nav).queryByRole("button", { name: "Proposed types" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Review proposed types" })).toBeNull();
    expect(sent.some(({ path }) => path.includes("link-types"))).toBe(false);
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
      if (path === "people/u1/disable-plan") return json(200, { person: "u1", items: [], not_yet_listed: ["boards"] });
      if (path === "people/u1/disable") return json(200, { ...PERSON, enabled: false });
      if (path === "people/u1/enable") return json(200, { ...PERSON, enabled: true });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable osprey-demo-analyst" }));
    expect(sent.some((s) => s.path === "POST people/u1/disable")).toBe(false);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm disabling osprey-demo-analyst" }));
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

// ADR-114 Amendment 5 (B4d): the Demo packs tab — show and explain; the Glass runs nothing.
const PACKS = [
  { id: "operation-ledger", title: "Operation Ledger — preventive AML (synthetic)", shows: "A structuring ring.",
    delivery: "seed", licence: "Generated by OspreyFlow, owned outright", attribution: null,
    case_name: "Operation Ledger (synthetic demo)", loaded_case_id: "c-ledger", command: "ospreyflow demo add operation-ledger",
    source_page: null, size_bytes: null },
  { id: "paysim", title: "PaySim — mobile-money fraud (simulated)", shows: "6.36 million transactions.",
    delivery: "download", licence: "CC-BY-SA-4.0", attribution: "Lopez-Rojas, Elmir and Axelsson (2016)",
    case_name: "PaySim mobile money (internal)", loaded_case_id: null,
    command: "ospreyflow demo add paysim --file <the downloaded PS_20174392719_1491204439457_log.csv>",
    source_page: "https://www.kaggle.com/datasets/ealaxi/paysim1", size_bytes: 493534783 },
  { id: "enron", title: "Enron — a real company's email", shows: "About 150 people's real email.",
    delivery: "download", licence: "None stated", attribution: "CMU", case_name: "Enron corpus (real data, this machine only)",
    loaded_case_id: null, command: "ospreyflow demo add enron --file <the downloaded enron_mail_20150507.tar.gz>",
    source_page: "https://www.cs.cmu.edu/~enron/", size_bytes: 443254787, real_data: true },
];  // prettier-ignore

describe("the Demo packs tab", () => {
  it("shows each pack, its licence and credit, whether it is loaded, and the command that adds it", async () => {
    serve((path) => (path === "demo-packs" ? json(200, PACKS) : null));
    place(["administer_system"]);
    fireEvent.click(await screen.findByRole("button", { name: "Demo packs" }));
    expect(await screen.findByText("PaySim — mobile-money fraud (simulated)")).toBeTruthy();
    expect(screen.getByText(/CC-BY-SA-4.0/)).toBeTruthy();
    expect(screen.getByText(/Lopez-Rojas, Elmir and Axelsson/)).toBeTruthy();
    expect(screen.getByText("Loaded, in “Operation Ledger (synthetic demo)”.")).toBeTruthy();
    const paysim = screen.getByRole("article", { name: "PaySim — mobile-money fraud (simulated)" });
    expect(within(paysim).getByText("Not in any case you can open.")).toBeTruthy();
    expect(screen.getByText("ospreyflow demo add operation-ledger")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download PaySim's file/ }).getAttribute("href")).toBe(
      "https://www.kaggle.com/datasets/ealaxi/paysim1",
    );
  });

  it("says which pack is real people's data, and only that one (ADR-114 Amendment 23 point 4)", async () => {
    serve((path) => (path === "demo-packs" ? json(200, PACKS) : null));
    place(["administer_system"]);
    fireEvent.click(await screen.findByRole("button", { name: "Demo packs" }));
    const enron = await screen.findByRole("article", { name: "Enron — a real company's email" });
    expect(within(enron).getByRole("note").textContent).toMatch(/^Real personal data\./);
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });

  it("copies a pack's command, and says so", async () => {
    serve((path) => (path === "demo-packs" ? json(200, PACKS) : null));
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    place(["administer_system"]);
    fireEvent.click(await screen.findByRole("button", { name: "Demo packs" }));
    fireEvent.click(await screen.findByRole("button", { name: "Copy the command for operation-ledger" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("ospreyflow demo add operation-ledger"));
    expect(await screen.findByText("Copied. Run it in a terminal on the machine OspreyFlow runs on.")).toBeTruthy();
  });
});

// ADR-144 decision 6 (L2.5b): the System tab says how many cases made from another became views,
// in how many cases, and how many wait, as the Conduit counted them in the administrator's unit.
describe("the System tab's cases converted to views", () => {
  it("says the counts, and that the dry-run report says why each waiting case was not placed", async () => {
    serve((path) =>
      path === "system" ? json(200, { components: [], converted_views: { views: 3, cases: 2, waiting: 1 } }) : null,
    );
    place(["administer_system"], "System");
    const section = await screen.findByRole("region", { name: "Cases converted to views" });
    expect(section.textContent).toContain("3 cases made from another became views, in 2 cases of your unit.");
    expect(section.textContent).toContain("1 case is still made from another: the conversion's dry-run report");
    expect(section.textContent?.toLowerCase()).not.toContain("branch");
  });

  it("says when nothing became a view and nothing waits, and nothing when the count is not known", async () => {
    expect(convertedWords({ views: 0, cases: 0, waiting: 0 })).toEqual([
      "No case made from another has become a view in your unit.",
      "None is waiting to be converted.",
    ]);
    expect(convertedWords({ views: 1, cases: 1, waiting: 2 })[0]).toBe(
      "1 case made from another became a view, in 1 case of your unit.",
    );
    serve((path) => (path === "system" ? json(200, { version: "1.2", components: [] }) : null));
    place(["administer_system"], "System");
    await screen.findByRole("region", { name: "Version" });
    expect(screen.queryByRole("region", { name: "Cases converted to views" })).toBeNull();
  });
});

// ADR-114 decision 11: the System tab says where each model runs, and when case content leaves.
describe("the System tab's models", () => {
  it("shows each role's model and where it runs, with the notice when content leaves", async () => {
    serve((path) =>
      path === "system"
        ? json(200, {
            version: "1.2", components: [],
            models: [
              { role: "extraction", model: "openai/gpt-4o-mini", runs_at: "openai", local_model: "qwen2.5:7b-instruct" },
              { role: "vision", model: "moondream", runs_at: "this deployment", local_model: "moondream" },
            ],
            model_notice: "Case content with handling code P is sent to openai for extraction. Anything else runs on this deployment's own models.",
          })
        : null,
    );  // prettier-ignore
    place(["administer_system"], "System");
    const table = await screen.findByRole("table", { name: "Models" });
    expect(table.textContent).toContain("openai/gpt-4o-mini");
    expect(table.textContent).toContain("this deployment");
    expect((await screen.findByRole("note")).textContent).toContain("is sent to openai for extraction");
  });

  it("has no notice when every model runs here", async () => {
    serve((path) =>
      path === "system"
        ? json(200, { components: [], models: [{ role: "extraction", model: "qwen", runs_at: "this deployment", local_model: "qwen" }], model_notice: null })
        : null,
    );  // prettier-ignore
    place(["administer_system"], "System");
    await screen.findByRole("table", { name: "Models" });
    expect(screen.queryByRole("note")).toBeNull();
  });
});

// ADR-135 decision 5: the System tab shows each engine, its models, the roles it is the default
// for, and whether its key is present: Yes or No, never the key.
describe("the System tab's engines", () => {
  it("lists each engine with its models, the roles it is the default for and whether its key is present", async () => {
    serve((path) =>
      path === "system"
        ? json(200, {
            components: [], models: [], model_notice: null,
            engines: [
              { name: "local", label: "This deployment's own model", models: { extraction: "qwen2.5:7b-instruct", embedding: "all-minilm" }, default_for: ["embedding"], key_present: true },
              { name: "gemini", label: "Gemini", models: { extraction: "gemini/gemini-2.5-flash" }, default_for: ["extraction"], key_present: true,
                privacy_contract: true, contract_reference: "DPA 2026/07" },
              { name: "openai", label: "OpenAI", models: { vision: "openai/gpt-4o-mini" }, default_for: [], key_present: false, privacy_contract: false },
            ],
          })
        : null,
    );  // prettier-ignore
    place(["administer_system"], "System");
    const table = await screen.findByRole("table", { name: "Engines" });
    const rows = within(table).getAllByRole("row").slice(1).map((row) =>
      within(row).getAllByRole("cell").map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["This deployment's own model", "extraction: qwen2.5:7b-instruct; embedding: all-minilm", "embedding", "Yes", "Not needed: nothing leaves"],
      ["Gemini", "extraction: gemini/gemini-2.5-flash", "extraction", "Yes", "Under contract (DPA 2026/07)"],
      ["OpenAI", "vision: openai/gpt-4o-mini", "None", "No", "No contract"],
    ]);
    // ADR-136 decision 1: the privacy-contract mark, beside each engine.
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Engine", "Models", "Default for", "Key present", "Privacy contract",
    ]);  // prettier-ignore
  });

  it("never shows a key, even one the response wrongly carried", async () => {
    serve((path) =>
      path === "system"
        ? json(200, {
            components: [], models: [], model_notice: null,
            engines: [{ name: "gemini", label: "Gemini", models: { extraction: "gemini/x" }, default_for: [], key_present: true, key: "AIza-not-a-real-key" }],
          })
        : null,
    );  // prettier-ignore
    place(["administer_system"], "System");
    await screen.findByRole("table", { name: "Engines" });
    expect(document.body.textContent).not.toContain("AIza-not-a-real-key");
  });
});

// ADR-114 decision 13, Amendment 8 point 2: the version and the last update check.
describe("the System tab's version", () => {
  it("says the version and an update offered, with its notes and address", async () => {
    serve((path) =>
      path === "system"
        ? json(200, {
            version: "v0.4.1", components: [], models: [], model_notice: null,
            update: { current: "v0.4.1", checked_at: "2026-10-13T08:00:00Z", latest: "v0.5.0", update_available: true,
                      notes: "- Find connections", url: "https://github.com/acme/ospreyflow/releases/tag/v0.5.0", problem: null },
          })
        : null,
    );  // prettier-ignore
    place(["administer_system"], "System");
    const version = await screen.findByRole("region", { name: "Version" });
    expect(version.textContent).toContain("OspreyFlow v0.4.1");
    expect(version.textContent).toContain("v0.5.0 is available.");
    expect(version.textContent).toContain("ospreyflow update");
    expect(version.textContent).toContain("- Find connections");
    expect(screen.getByRole("link", { name: "The v0.5.0 release" }).getAttribute("href")).toBe(
      "https://github.com/acme/ospreyflow/releases/tag/v0.5.0",
    );
  });

  it("says when there has been no check", async () => {
    serve((path) => (path === "system" ? json(200, { version: "v0.4.1", components: [], models: [], model_notice: null, update: null }) : null));
    place(["administer_system"], "System");
    const version = await screen.findByRole("region", { name: "Version" });
    expect(version.textContent).toContain("Not checked for updates yet.");
    expect(version.textContent).toContain("ospreyflow update --check");
  });
});


// ADR-136 decision 2: each dataset's egress, set by an administrator.
describe("the Datasets tab", () => {
  const DATASETS = [
    { id: "enron", name: "Enron corpus", owning_unit: "verify", egress: "none" },
    { id: "fixture-corp", name: "Fixture Corp", owning_unit: "verify", egress: "contracted" },
  ];

  it("is the system administrator's, and says what each setting means and that none is the default", async () => {
    serve((path) => (path === "datasets" ? json(200, DATASETS) : null));
    place(["manage_people"]);
    expect(screen.queryByRole("button", { name: "Datasets" })).toBeNull();
    cleanup();
    serve((path) => (path === "datasets" ? json(200, DATASETS) : null));
    place(["administer_system"]);
    fireEvent.click(screen.getByRole("button", { name: "Datasets" }));
    const table = await screen.findByRole("table", { name: "Datasets" });
    const egress = within(table).getByLabelText("Egress for Enron corpus") as HTMLSelectElement;
    expect(egress.value).toBe("none");
    expect(Array.from(egress.options).map((o) => o.value)).toEqual(["none", "contracted", "any"]);
    expect(screen.getByText(/Every dataset is none until you change it/)).toBeTruthy();
  });

  it("saves one dataset's egress and says so", async () => {
    const sent = serve((path, init) =>
      path === "datasets"
        ? json(200, DATASETS)
        : path === "datasets/enron/egress" && init?.method === "PUT"
          ? json(200, { ...DATASETS[0], egress: "any" })
          : null,
    );
    place(["administer_system"]);
    fireEvent.click(screen.getByRole("button", { name: "Datasets" }));
    fireEvent.change(await screen.findByLabelText("Egress for Enron corpus"), { target: { value: "any" } });
    fireEvent.click(screen.getByRole("button", { name: "Save egress for Enron corpus" }));
    await waitFor(() => expect(sent.some((s) => s.path === "PUT datasets/enron/egress")).toBe(true));
    expect(sent.find((s) => s.path === "PUT datasets/enron/egress")?.body).toEqual({ egress: "any" });
    expect(await screen.findByText("Enron corpus: egress is now any.")).toBeTruthy();
  });

  it("says a refusal in words and leaves the setting as it was", async () => {
    serve((path, init) =>
      path === "datasets"
        ? json(200, DATASETS)
        : path === "datasets/enron/egress" && init?.method === "PUT"
          ? json(403, { detail: "forbidden" })
          : null,
    );
    place(["administer_system"]);
    fireEvent.click(screen.getByRole("button", { name: "Datasets" }));
    fireEvent.change(await screen.findByLabelText("Egress for Enron corpus"), { target: { value: "any" } });
    fireEvent.click(screen.getByRole("button", { name: "Save egress for Enron corpus" }));
    expect(await screen.findByText("Your account does not hold the right for this.")).toBeTruthy();
    expect(screen.queryByText("Enron corpus: egress is now any.")).toBeNull();
  });
});

// ADR-112 Amendment 3 (build order step 33 (a)): remove a person, only once confirmed in words.
describe("people: remove", () => {
  it("removes a person only once the words are confirmed, and says what became of their work", async () => {
    const sent = serve((path, init) => (path === "people/u1" && init?.method === "DELETE" ? json(200, PERSON) : null));
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Remove osprey-demo-analyst" }));
    const asked = screen.getByRole("group", { name: "Remove osprey-demo-analyst" });
    expect(asked.textContent).toContain("Remove Demo Analyst (osprey-demo-analyst)? Their account is deleted");
    expect(asked.textContent).toContain("show their id in place of their name");
    expect(asked.textContent).toContain("disable it instead");
    expect(sent.some((s) => s.path === "DELETE people/u1")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Confirm removing osprey-demo-analyst" }));
    expect(await screen.findByText(/Demo Analyst \(osprey-demo-analyst\) was removed/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Remove osprey-demo-analyst" })).toBeNull();
    expect(sent.filter((s) => s.path === "DELETE people/u1")).toHaveLength(1);
  });

  it("keeps the person when the removal is not confirmed", async () => {
    const sent = serve();
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Remove osprey-demo-analyst" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep osprey-demo-analyst" }));
    expect(screen.queryByRole("group", { name: "Remove osprey-demo-analyst" })).toBeNull();
    expect(sent.some((s) => s.path.startsWith("DELETE"))).toBe(false);
    expect(screen.getByText("Demo Analyst")).toBeTruthy();
  });

  it("says a refusal in the Conduit's words and keeps the person listed", async () => {
    const words = "osprey-demo-analyst is the only enabled person who can manage people. Give someone else the Admin role first.";
    serve((path, init) =>
      path === "people/u1" && init?.method === "DELETE" ? json(409, { error: "last_administrator", detail: words }) : null,
    );
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Remove osprey-demo-analyst" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm removing osprey-demo-analyst" }));
    expect(await screen.findByText(words)).toBeTruthy();
    expect(screen.getByText("Demo Analyst")).toBeTruthy();
  });

  it("says removing your own account is refused", async () => {
    serve((path, init) =>
      path === "people/u1" && init?.method === "DELETE" ? json(409, { detail: { error: "cannot_remove_yourself" } }) : null,
    );
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Remove osprey-demo-analyst" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm removing osprey-demo-analyst" }));
    expect(await screen.findByText("You cannot remove your own account.")).toBeTruthy();
  });

  it("offers no removal of an account OspreyFlow itself uses", async () => {
    serve((path) =>
      path === "people"
        ? json(200, [PERSON, { id: "u9", username: "osprey-verify-probe", name: "osprey-verify-probe", enabled: true, roles: [],
                              system_account: true }])  // prettier-ignore
        : null,
    );
    place(["manage_people"]);
    await screen.findByRole("button", { name: "Remove osprey-demo-analyst" });
    expect(screen.queryByRole("button", { name: "Remove osprey-verify-probe" })).toBeNull();
  });
});

// ADR-112 Amendment 3 (build order step 33 (b)): a refused organisation arrival joined to an account.
const ARRIVAL = { subject: "sub-1", provider_username: "pat.example", last_refused: "2026-11-05T09:30:00Z", attempts: 2 };

describe("people: join a refused organisation arrival", () => {
  it("offers the arrival, and joins it only once the words are confirmed", async () => {
    const sent = serve((path, init) => {
      if (path === "organisation-arrivals") return json(200, [ARRIVAL]);
      if (path === "people/u1/organisation-link" && init?.method === "POST") return json(200, { ...PERSON, organisation_linked: true });
      return null;
    });
    place(["manage_people"]);
    const section = await screen.findByRole("region", { name: "Refused organisation sign-ins" });
    expect(section.textContent).toContain("pat.example");
    expect(section.textContent).toContain("Refused 2 times, last at 2026-11-05 09:30 UTC");
    fireEvent.click(within(section).getByRole("button", { name: "Join pat.example" }));
    const asked = screen.getByRole("group", { name: "Join pat.example" });
    expect(asked.textContent).toContain("Join pat.example to Demo Analyst (osprey-demo-analyst)?");
    expect(asked.textContent).toContain("only if you are sure they are the same person");
    expect(sent.some((s) => s.path.endsWith("organisation-link"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Confirm joining pat.example" }));
    expect(await screen.findByText(/pat.example is joined to osprey-demo-analyst/)).toBeTruthy();
    expect(sent.find((s) => s.path === "POST people/u1/organisation-link")?.body).toEqual({ subject: "sub-1" });
    expect(screen.queryByRole("region", { name: "Refused organisation sign-ins" })).toBeNull();
    expect(screen.getByText("Signs in through the organisation")).toBeTruthy();
  });

  it("offers no account OspreyFlow itself uses, and none already joined", async () => {
    serve((path) => {
      if (path === "organisation-arrivals") return json(200, [ARRIVAL]);
      if (path === "people")
        return json(200, [
          PERSON,
          { id: "u8", username: "joined.person", name: "Joined Person", enabled: true, roles: [], organisation_linked: true },
          { id: "u9", username: "osprey-verify-probe", name: "osprey-verify-probe", enabled: true, roles: [], system_account: true },
        ]);
      return null;
    });
    place(["manage_people"]);
    const choice = (await screen.findByLabelText("Account to join pat.example to")) as HTMLSelectElement;
    expect([...choice.options].map((o) => o.textContent)).toEqual(["Demo Analyst (osprey-demo-analyst)"]);
  });

  it("says a refused join in the Conduit's words", async () => {
    const words = "osprey-demo-analyst is already joined to an organisation account.";
    serve((path, init) => {
      if (path === "organisation-arrivals") return json(200, [ARRIVAL]);
      if (path === "people/u1/organisation-link" && init?.method === "POST") return json(409, { error: "already_linked", detail: words });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Join pat.example" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm joining pat.example" }));
    expect(await screen.findByText(words)).toBeTruthy();
  });

  it("shows nothing when nobody was refused", async () => {
    serve();
    place(["manage_people"]);
    await screen.findByText("Demo Analyst");
    expect(screen.queryByRole("region", { name: "Refused organisation sign-ins" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Roles, teams and Authors from Admin (ADR-145 Amendment 4 decision 12)", () => {
  it("opens the one help page and comes back to Admin", () => {
    serve();
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
    fireEvent.click(screen.getByRole("button", { name: "Roles, teams and Authors" }));
    expect(screen.getByRole("heading", { level: 2, name: "Roles, teams and Authors" })).toBeTruthy();
    const back = screen.getByRole("button", { name: "← Back to Admin" });
    expect(document.activeElement).toBe(back);
    fireEvent.click(back);
    expect(screen.getByRole("navigation", { name: "Admin sections" })).toBeTruthy();
  });
});
