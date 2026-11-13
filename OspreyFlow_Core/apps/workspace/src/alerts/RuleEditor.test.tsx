// @vitest-environment jsdom
// The rule editor (ADR-146 decision 3, L2.11): the dataset is chosen first; the conditions are
// offered from that dataset's live model alone, never the deployment's ontology (red with a second
// dataset's type offered); where its alerts go is said before saving; a draft is tested before it
// may go live, and a dataset that asks for a second person says so. The data is synthetic (rule 9).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema } from "../../../../packages/schemas/generated";
import { RuleEditor } from "./RuleEditor";
import BPMN from "./ruleStandards/fixtures/visits-to-listed-people.bpmn?raw";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const person = (name: string) => ({ name, pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
  { name: "family_name", type: "string" }] }); // prettier-ignore
const ontology = (...types: string[]) => ({ version: 1, entity_types: types.map(person), edge_types: [] }) as unknown as OntologySchema;

const PRISON = { id: "ds-prison", name: "Prison records", kind: "source", second_person: false, ontology: ontology("Person", "Prisoner"), lists: [
  { id: "l-prison", name: "Prison watch", kind: "screening", version: 1, deployment_wide: false },
  { id: "l-uk", name: "UK sanctions", kind: "screening", version: 3, deployment_wide: true },
  { id: "l-codes", name: "Wing codes", kind: "reference", version: 1, deployment_wide: false },
] }; // prettier-ignore
const FINANCE = { id: "ds-finance", name: "Ledger", kind: "source", second_person: true, ontology: ontology("Account"), lists: [] };
const DRAFT = { id: "r1", investigation_id: "c1", owner_id: "me", name: "Okafor", created_at: "2026-11-10T09:00:00Z", trigger: "post_commit",
  budget_ms: 5000, status: "draft", version: 1, dataset_id: "ds-prison",
  params: { typology: "sentence", pattern_id: "p", sentence: { subject: "Person" } } }; // prettier-ignore

type Call = { method: string; path: string; body: unknown };
type Answer = (body: unknown) => Response | Promise<Response>;
function serve(routes: Record<string, Answer>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, path, body });
      const answer = routes[`${method} ${path}`] ?? routes[path];
      return answer ? answer(body) : json(404, {});
    }),
  );
  return calls;
}

const DEPLOYMENT_WIDE = ontology("Person", "Prisoner", "Account", "Vessel");

function world(over: Record<string, Answer> = {}) {
  return serve({
    "rules/datasets": () => json(200, [PRISON, FINANCE]),
    "alert-teams": () => json(200, [{ role_id: "team-7", display_name: "Prison intel", lead: false, members: [], member_count: 6 }]),
    // The deployment's ontology: the editor must never offer from it.
    "/v1/ontology": () => json(200, DEPLOYMENT_WIDE),
    "POST rules/drafts": () => json(201, DRAFT),
    "POST rules/r1/test": () => json(200, { rule_id: "r1", version: 1, days: 30, would_raise: 3, words: "…" }),
    "POST rules/r1/make-live": () => json(200, { ...DRAFT, status: "active" }),
    "rules/r1/export.bpmn": () => new Response(BPMN, { status: 200 }),
    ...over,
  });
}

const editor = () =>
  render(<RuleEditor apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" patterns={[]} canMakeLive onChanged={vi.fn()} />);

async function choose(name: string) {
  fireEvent.change(await screen.findByLabelText("The dataset this rule watches"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Choose the dataset" }));
}

describe("the rule editor (ADR-146 decision 3)", () => {
  it("asks for the dataset first and offers only the case's", async () => {
    world();
    editor();
    const picker = await screen.findByLabelText("The dataset this rule watches");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose one…", "Prison records", "Ledger"]);
    expect(screen.queryByRole("form", { name: /Write a rule on/ })).toBeNull();
  });

  it("offers the conditions from the dataset's live model, never another dataset's or the deployment's", async () => {
    world();
    editor();
    await choose("ds-prison");
    const subject = await screen.findByLabelText("Subject");
    const offered = within(subject).getAllByRole("option").map((o) => o.textContent ?? "");
    expect(offered.some((o) => o.includes("Prisoner"))).toBe(true);
    expect(offered.some((o) => o.includes("Account") || o.includes("Vessel"))).toBe(false);
  });

  it("says where its alerts go before saving, with how many of the team hold the case", async () => {
    // The teams answer after the dataset is chosen, as a slow real read can: the team select is
    // drawn before its teams arrive, and a choice made then is of an option not yet there.
    world({
      "alert-teams": async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return json(200, [{ role_id: "team-7", display_name: "Prison intel", lead: false, members: [], member_count: 6 }]);
      },
    });
    editor();
    await choose("ds-prison");
    const goesTo = await screen.findByLabelText("Alert goes to (team)");
    // Choose the team only once it is offered: its membership is what the sentence counts.
    await within(goesTo).findByRole("option", { name: "Prison intel only" });
    fireEvent.change(goesTo, { target: { value: "team:team-7" } });
    expect(screen.getByLabelText("Where its alerts go").textContent).toBe(
      "Its alerts will appear in Alerts, seen by the 6 members of Prison intel who hold this case and the home case's Authors.",
    );
  });

  it("saves a draft on its dataset, and makes it live only once tested", async () => {
    const calls = world();
    editor();
    await choose("ds-prison");
    fireEvent.change(await screen.findByLabelText("Name of the rule"), { target: { value: "Okafor" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    const live = await screen.findByRole("button", { name: "Make live" });
    expect((calls.find((c) => c.path === "rules/drafts")?.body as { dataset_id: string }).dataset_id).toBe("ds-prison");
    expect((live as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Test on the last 30 days" }));
    expect((await screen.findByLabelText("Test result")).textContent).toContain("It would have raised 3 alerts in the last 30 days.");
    await waitFor(() => expect((live as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(live);
    await waitFor(() => expect(calls.some((c) => c.path === "rules/r1/make-live")).toBe(true));
  });

  it("offers the screening lists the dataset may read, and saves the one chosen", async () => {
    const calls = world();
    editor();
    await choose("ds-prison");
    fireEvent.change(await screen.findByLabelText("Relationship"), { target: { value: "on_screening_list" } });
    const picker = await screen.findByLabelText("Screening list");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a list…", "Prison watch", "UK sanctions (subscribed)"]);
    fireEvent.change(picker, { target: { value: "l-uk" } });
    fireEvent.change(screen.getByLabelText("Name of the rule"), { target: { value: "Listed visitors" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    await waitFor(() => expect(calls.some((c) => c.path === "rules/drafts")).toBe(true));
    const sent = calls.find((c) => c.path === "rules/drafts")?.body as { sentence: { relationship: { list_id?: string } } };
    expect(sent.sentence.relationship.list_id).toBe("l-uk");
  });

  it("shows the saved draft as BPMN, drawn from the files saved beside it (ADR-146 Amendment 5)", async () => {
    const calls = world();
    editor();
    await choose("ds-prison");
    fireEvent.change(await screen.findByLabelText("Name of the rule"), { target: { value: "Okafor" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    fireEvent.click(await screen.findByRole("button", { name: "Show as BPMN" }));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(calls.some((c) => c.path === "rules/r1/export.bpmn")).toBe(true);
  });

  it("opens an existing rule at its draft, on its own dataset, ready to make live once tested (ADR-146 decision 5)", async () => {
    world({
      "rules/r1/draft": () => json(200, { rule_id: "r1", version: 2, action: "change", name: "Okafor, changed", status: "draft",
        params: { typology: "sentence", pattern_id: "p", sentence: { subject: "Prisoner", conditions: [], severity: "low", team: "case", runs: "post_commit", on_hit: "load", scope: "this_case" } },
        trigger: "post_commit", budget_ms: 5000, proposed_by: "me", proposed_at: "2026-11-10T09:00:00Z",
        tested_at: "2026-11-10T10:00:00Z", tested_by: "me", tested_days: 30, would_raise: null }),
    }); // prettier-ignore
    const live = { ...DRAFT, status: "active", name: "Okafor" };
    render(<RuleEditor apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" patterns={[]} canMakeLive onChanged={vi.fn()} opening={live as never} />);
    expect(((await screen.findByLabelText("Name of the rule")) as HTMLInputElement).value).toBe("Okafor, changed");
    expect((screen.getByLabelText("Subject") as HTMLSelectElement).value).toBe("Prisoner");
    expect(screen.queryByLabelText("The dataset this rule watches")).toBeNull(); // its dataset is fixed
    expect(screen.getByText(/This draft was tested on/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Make live" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("says a dataset asks for a second person before it is made live", async () => {
    world({ "POST rules/drafts": () => json(201, { ...DRAFT, dataset_id: "ds-finance", params: { ...DRAFT.params, sentence: { subject: "Account" } } }) });
    editor();
    await choose("ds-finance");
    fireEvent.change(await screen.findByLabelText("Name of the rule"), { target: { value: "Ledger rule" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    expect(await screen.findByText(/Ledger asks for a second person/)).toBeTruthy();
  });

  it("offers Make live only to someone who holds deploy_rules; a Rule author saves and tests", async () => {
    world();
    render(<RuleEditor apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" patterns={[]} canMakeLive={false} onChanged={vi.fn()} />);
    await choose("ds-prison");
    fireEvent.change(await screen.findByLabelText("Name of the rule"), { target: { value: "Okafor" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    expect(await screen.findByRole("button", { name: "Test on the last 30 days" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Make live" })).toBeNull();
  });

  it("is written by a case Author alone", () => {
    world();
    render(<RuleEditor apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="viewer" patterns={[]} canMakeLive onChanged={vi.fn()} />);
    expect(screen.getByText("A case Author writes the case's rules.")).toBeTruthy();
    expect(screen.queryByLabelText("The dataset this rule watches")).toBeNull();
  });
});
