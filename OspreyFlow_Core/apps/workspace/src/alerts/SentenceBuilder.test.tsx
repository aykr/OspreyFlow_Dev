// @vitest-environment jsdom
// ADR-133 decisions 1 and 3, stage (b): a rule written as a sentence. Every blank is offered from the
// ontology (a `sensitivity: high` property, a system link and a link with no dated events are never
// offered where they cannot be used); the draft becomes the server's sentence and back; "Preview on
// the last 90 days" says the count and up to five examples, or why it was refused; deploying posts
// the sentence; the whole deployment is offered to an administrator only.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RuleSentence } from "../../../../packages/schemas/generated";
import { SentenceBuilder } from "./SentenceBuilder";
import { emptyDraft, eventLinksFor, fromSentence, linksFor, opsFor, propertiesFor, sentenceSummary, toSentence } from "./sentence";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const ONTOLOGY = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
      { name: "family_name", type: "string", indexed: true },
      { name: "date_of_birth", type: "date", sensitivity: "high" },
      { name: "listing", type: "enum", values: ["sanction", "pep", "adverse_media"] }] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", identifiers: [], properties: [
      { name: "value_normalised", type: "string", indexed: true }] },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", identifiers: [], properties: [
      { name: "geometry_ref", type: "string" }] },
    { name: "Alert", pole_class: "event", channel: "rose", shape: "triangle", identifiers: [], properties: [] },
  ],
  edge_types: [
    { name: "USES", from: ["Person"], to: ["Endpoint"], basis: "direct" },
    { name: "PRESENT_AT", from: ["Person"], to: ["Location"], temporal: true, basis: "direct", label: "Present at" },
    { name: "TRANSACTED", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct",
      properties: [{ name: "amount", type: "float" }, { name: "transaction_type", type: "enum", values: ["CASH_IN"] }] },
    { name: "ALERTED_ON", from: ["Alert"], to: ["*"], system: true, basis: "probabilistic" },
  ],
} as unknown as OntologySchema; // prettier-ignore

const EXAMPLES = ["Okafor", "Adeyemi", "Brennan", "Clarke", "Dunmore"].map((n, i) => ({
  node_id: `p${i}`, name: n, entity_type: "Person", words: `${n} (Person)` })); // prettier-ignore

function serve(answer: (path: string, body: unknown) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      sent.push({ path, body });
      const answered = answer(path, body);
      if (answered) return answered;
      if (path === "/v1/ontology") return json(200, ONTOLOGY);
      if (path === "rules/preview") return json(200, { days: 90, would_raise: 7, examples: EXAMPLES, words: "When a Person…" });
      if (path === "rules/sentence/compile")
        return json(200, { words: "When a Person whose listing is one of sanction, pep, raise a medium-severity alert for the case team, after each load commits.",
          pattern: { nodes: [{ var: "subject", entity_type: "Person", where: {} }], edges: [], limit: 50000 } }); // prettier-ignore
      if (path === "rules/sentence") return json(201, { id: "r9", name: "Listed", investigation_id: "c1", owner_id: "a", created_at: "", params: { typology: "sentence", pattern_id: "p", sentence: body } });
      return json(404, {});
    }),
  );
  return sent;
}

function builder(level: "viewer" | "editor" | "author" = "author", isAdministrator = false, patterns: unknown[] = []) {
  const onDeployed = vi.fn();
  render(
    <SentenceBuilder apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level={level} isAdministrator={isAdministrator}
      patterns={patterns as never} onDeployed={onDeployed} />, // prettier-ignore
  );
  return onDeployed;
}

async function listedPeople() {
  fireEvent.click(await screen.findByRole("button", { name: "Add a condition" }));
  fireEvent.change(screen.getByLabelText("Condition 1: property"), { target: { value: "listing" } });
  fireEvent.change(screen.getByLabelText("Condition 1: test"), { target: { value: "one_of" } });
  fireEvent.click(screen.getByLabelText("Condition 1: sanction"));
  fireEvent.click(screen.getByLabelText("Condition 1: pep"));
}

describe("what the ontology offers", () => {
  it("never offers a sensitivity: high property, and offers the tests a property's type fits", () => {
    expect(propertiesFor(ONTOLOGY, "Person").map((p) => p.name)).toEqual(["family_name", "listing"]);
    const [family, listing] = propertiesFor(ONTOLOGY, "Person");
    expect(opsFor(family)).toEqual(["equals", "one_of"]);
    expect(opsFor(listing)).toEqual(["equals", "one_of"]);
    expect(opsFor({ name: "amount", type: "float" } as never)).toEqual(["equals", "above", "below"]);
    expect(opsFor({ name: "geometry_ref", type: "string" } as never)).toContain("within_area");
  });

  it("offers declared link types only, never a system one, and only dated ones to count", () => {
    expect(linksFor(ONTOLOGY, "Person").map((l) => l.name)).toEqual(["USES", "PRESENT_AT"]);
    expect(eventLinksFor(ONTOLOGY, "Person").map((l) => l.name)).toEqual(["PRESENT_AT"]);
    expect(linksFor(ONTOLOGY, "Endpoint").map((l) => l.name)).not.toContain("ALERTED_ON");
  });

  it("turns the draft into the server's sentence and back", () => {
    const draft = { ...emptyDraft("Person"), relationship: "linked" as const, linkType: "USES", otherType: "Endpoint",
      frequency: "count" as const, frequencyLink: "PRESENT_AT", severity: "high" as const }; // prettier-ignore
    draft.conditions = [{ property: "listing", op: "one_of", values: ["sanction", "pep"], value: "", start: "", end: "",
      area: { name: "x", west: "", south: "", east: "", north: "" } }]; // prettier-ignore
    const sentence = toSentence(draft);
    expect(sentence).toMatchObject({
      subject: "Person",
      conditions: [{ op: "one_of", property: "listing", values: ["sanction", "pep"] }],
      relationship: { kind: "linked", link_type: "USES", other_type: "Endpoint" },
      frequency: { kind: "count", link_type: "PRESENT_AT", at_least: 3, within_days: 7 },
      severity: "high", scope: "this_case", runs: "post_commit", on_hit: "load",
    });
    expect(toSentence(fromSentence(sentence))).toEqual(sentence);
    expect(sentenceSummary(sentence)).toBe(
      "When a Person whose listing is one of sanction, pep, is linked by USES to an Endpoint, 3 or more times by PRESENT_AT within 7 day(s): a high-severity alert for the case team.",
    );
  });

  it("a rule just for its author never holds a case's rows", () => {
    const sentence = toSentence({ ...emptyDraft(), scope: "just_me", runs: "pre_commit", onHit: "hold", team: "my_team" });
    expect(sentence).toMatchObject({ scope: "just_me", runs: "post_commit", on_hit: "load", team: "case" } as Partial<RuleSentence>);
  });
});

describe("the sentence builder", () => {
  it("previews the rule on the last 90 days: the count, up to five examples, and that nothing was written", async () => {
    const sent = serve();
    builder();
    await listedPeople();
    fireEvent.click(screen.getByRole("button", { name: "Preview on the last 90 days" }));
    const preview = await screen.findByRole("region", { name: "Preview" });
    expect(within(preview).getByRole("status").textContent).toContain("It would have raised 7 alerts in the last 90 days.");
    expect(within(preview).getByText("The first 5:")).toBeTruthy();
    expect(within(within(preview).getByRole("list", { name: "Preview examples" })).getAllByRole("listitem")).toHaveLength(5);
    expect(preview.textContent).toContain("Nothing was raised or written.");
    expect(sent.map((s) => s.path)).not.toContain("rules/sentence"); // a preview never deploys
    const asked = sent.find((s) => s.path === "rules/preview");
    expect(asked?.body).toMatchObject({ sentence: { subject: "Person", conditions: [{ op: "one_of", property: "listing", values: ["sanction", "pep"] }] } });
  });

  it("says in words when a preview is past the limit, and counts nothing", async () => {
    serve((path) => (path === "rules/preview" ? json(409, { error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50001 }) : null));
    builder();
    fireEvent.click(await screen.findByRole("button", { name: "Preview on the last 90 days" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Too many to preview: the rule's subjects number 50,001, past the limit of 50,000. Nothing was counted; narrow the sentence and preview again.");
    expect(screen.queryByRole("region", { name: "Preview" })).toBeNull();
  });

  it("says the server's refusal of a blank in words", async () => {
    serve((path) => (path === "rules/preview" ? json(422, { error: "sentence_refused", blank: "conditions[0]", reason: "unknown_property", detail: "'Person' declares no property 'x'" }) : null));
    builder();
    fireEvent.click(await screen.findByRole("button", { name: "Preview on the last 90 days" }));
    expect((await screen.findByRole("alert")).textContent).toContain("'Person' declares no property 'x'.");
  });

  it("shows the sentence's drawn pattern, its advanced view", async () => {
    serve();
    builder();
    await listedPeople();
    fireEvent.click(screen.getByRole("button", { name: "Show the drawn pattern" }));
    const pattern = await screen.findByRole("region", { name: "The drawn pattern" });
    expect(pattern.textContent).toContain("When a Person whose listing is one of sanction, pep");
    expect(pattern.textContent).toContain("open in the Query builder");
  });

  it("reads a saved pattern back as a sentence", async () => {
    serve((path) =>
      path === "rules/sentence/read"
        ? json(200, { subject: "Person", conditions: [{ op: "equals", property: "family_name", value: "Okafor" }], relationship: null, frequency: null })
        : null,
    );
    builder("author", false, [{ id: "s", pattern_id: "pat-1", version: 1, name: "Okafors", owner_id: "a", created_at: "", definition: { nodes: [], edges: [] } }]);
    fireEvent.change(await screen.findByLabelText("Read a saved pattern as a sentence"), { target: { value: "pat-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Read as a sentence" }));
    await waitFor(() => expect((screen.getByLabelText("Condition 1: value") as HTMLInputElement).value).toBe("Okafor"));
  });

  it("deploys a rule just for its author, and offers no other scope, an administrator's included (ADR-146 Amendment 6)", async () => {
    const sent = serve();
    const onDeployed = builder();
    await listedPeople();
    const scopes = () => [...(screen.getByLabelText("For (scope)") as HTMLSelectElement).options].map((o) => o.value);
    expect(scopes()).toEqual(["just_me"]);
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Name of the sentence rule"), { target: { value: "Listed people" } });
    fireEvent.click(screen.getByRole("button", { name: "Deploy the sentence" }));
    await waitFor(() => expect(onDeployed).toHaveBeenCalled());
    expect(sent.find((s) => s.path === "rules/sentence")?.body).toMatchObject({ name: "Listed people", sentence: { severity: "high", scope: "just_me" } });
    cleanup();
    serve();
    builder("author", true);
    await screen.findByLabelText("For (scope)");
    expect(scopes()).toEqual(["just_me"]);
  });

  it("lets an Editor deploy for themselves only, and a Viewer not at all", async () => {
    serve();
    builder("editor");
    fireEvent.change(await screen.findByLabelText("Name of the sentence rule"), { target: { value: "Mine" } });
    expect((screen.getByLabelText("For (scope)") as HTMLSelectElement).value).toBe("just_me");
    expect((screen.getByRole("button", { name: "Deploy the sentence" }) as HTMLButtonElement).disabled).toBe(false);
    cleanup();
    serve();
    builder("viewer");
    await screen.findByLabelText("Subject");
    expect(screen.queryByRole("button", { name: "Deploy the sentence" })).toBeNull();
    expect((screen.getByRole("button", { name: "Preview on the last 90 days" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("offers before-commit runs and holding only where the sentence allows them, on a case's rule in the editor", async () => {
    serve();
    render(
      <SentenceBuilder apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator={false}
        patterns={[]} onDeployed={vi.fn()}
        editor={{ dataset: { id: "ds-1", name: "Prison records", kind: "source", second_person: false, ontology: ONTOLOGY as never, lists: [] }, onSaved: vi.fn() }} />, // prettier-ignore
    );
    const runs = async () => [...((await screen.findByLabelText("Runs")) as HTMLSelectElement).options].map((o) => o.value);
    expect(await runs()).toEqual(["post_commit", "pre_commit", "schedule"]);
    fireEvent.change(screen.getByLabelText("Runs"), { target: { value: "pre_commit" } });
    expect(screen.getByLabelText("A hit")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Relationship"), { target: { value: "linked" } });
    // ADR-133 stage (d): a link is read from the stored graph, so after commit or on a schedule.
    expect(await runs()).toEqual(["post_commit", "schedule"]);
    expect(screen.getByText("A link is read from the stored graph, so this rule runs after each load commits.")).toBeTruthy();
  });
});
