// @vitest-environment jsdom
// ADR-133 stage (d) in the Monitoring place. Decision 1: a sentence runs on a schedule (every day,
// or every week on a day, at an hour), never for the whole deployment; the rules list says when it
// runs and shows its runs. Decision 7: a whole-deployment rule waiting for a second person says so,
// and offers Approve and Reject to an administrator-author who did not propose it; its versions say
// who made and decided each; closing a high-severity alert proposes the close, and a second member
// approves it or sends it back — never the member who proposed it. Amendment 3 item 4: a list's
// refresh schedule. The data is synthetic (rule 9).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, TypologyRule } from "../../../../packages/schemas/generated";
import { AlertQueue, closeNeedsSecondPerson, statusSentence } from "./AlertQueue";
import { ListsPanel, scheduleState } from "./ListsPanel";
import { pendingWords } from "./RuleChanges";
import { RulesPanel, runsWords, statusWords } from "./RulesPanel";
import { SentenceBuilder } from "./SentenceBuilder";
import { emptyDraft, fromSentence, scheduleWords, toSentence } from "./sentence";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
    { name: "listing", type: "enum", values: ["sanction", "pep"] }] }],
  edge_types: [],
} as unknown as OntologySchema; // prettier-ignore

const SENTENCE = { subject: "Person", conditions: [], severity: "high", team: "case", on_hit: "load" };
function rule(over: Partial<TypologyRule> & Record<string, unknown> = {}): TypologyRule {
  return {
    id: "r1", investigation_id: "c1", owner_id: "maker", name: "Sanctioned people", created_at: "2026-11-01T09:00:00Z",
    trigger: "post_commit", budget_ms: 5000, status: "active", version: 1,
    params: { typology: "sentence", pattern_id: "p1", sentence: { ...SENTENCE, runs: "post_commit", scope: "deployment" } },
    ...over,
  } as unknown as TypologyRule; // prettier-ignore
}

type Call = { method: string; path: string; body: unknown };
function serve(routes: Record<string, (body: unknown, method: string) => Response>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, path, body });
      const answer = routes[`${method} ${path}`] ?? routes[path];
      return answer ? answer(body, method) : json(404, {});
    }),
  );
  return calls;
}

describe("a rule on a schedule (decision 1)", () => {
  it("sends a weekly schedule with its day and hour, and reads it back", () => {
    const draft = { ...emptyDraft("Person"), runs: "schedule" as const, every: "weekly" as const, hour: "7", weekday: "1" };
    const sentence = toSentence(draft) as unknown as { runs: string; schedule: unknown };
    expect(sentence.runs).toBe("schedule");
    expect(sentence.schedule).toEqual({ every: "weekly", hour: 7, weekday: 1 });
    const back = fromSentence(sentence as never);
    expect([back.runs, back.every, back.hour, back.weekday]).toEqual(["schedule", "weekly", "7", "1"]);
    expect(scheduleWords({ every: "weekly", hour: 7, weekday: 1 })).toBe("every Monday at 07:00");
    expect(scheduleWords({ every: "daily", hour: 6 })).toBe("every day at 06:00");
  });

  it("never schedules a rule for the whole deployment", () => {
    const draft = { ...emptyDraft("Person"), runs: "schedule" as const, scope: "deployment" as const };
    const sentence = toSentence(draft) as unknown as { runs: string; schedule: unknown };
    expect([sentence.runs, sentence.schedule]).toEqual(["post_commit", undefined]);
  });

  it("offers the schedule's blanks in the builder and deploys them", async () => {
    const calls = serve({
      "/v1/ontology": () => json(200, ONTOLOGY),
      "POST rules/sentence": (body) => json(201, { ...rule(), params: { typology: "sentence", pattern_id: "p", sentence: (body as { sentence: unknown }).sentence } }),
    });
    render(<SentenceBuilder apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator={false} patterns={[]} onDeployed={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Runs"), { target: { value: "schedule" } });
    fireEvent.change(screen.getByLabelText("Every"), { target: { value: "weekly" } });
    fireEvent.change(screen.getByLabelText("On (day of the week)"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("At (hour, Europe/London)"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Name of the sentence rule"), { target: { value: "Weekly check" } });
    fireEvent.click(screen.getByRole("button", { name: "Deploy the sentence" }));
    await waitFor(() => expect(calls.some((c) => c.path === "rules/sentence")).toBe(true));
    const sent = calls.find((c) => c.path === "rules/sentence")!.body as { sentence: { runs: string; schedule: unknown } };
    expect(sent.sentence.runs).toBe("schedule");
    expect(sent.sentence.schedule).toEqual({ every: "weekly", hour: 8, weekday: 3 });
  });

  it("says when a scheduled rule runs, and its runs and why one did not", async () => {
    const scheduled = rule({ trigger: "schedule", params: { typology: "sentence", pattern_id: "p1",
      sentence: { ...SENTENCE, runs: "schedule", scope: "this_case", schedule: { every: "daily", hour: 6 } } } as never }); // prettier-ignore
    expect(runsWords(scheduled)).toBe("Runs on a schedule, every day at 06:00 (Europe/London), as its author");
    serve({
      "GET rules": () => json(200, [scheduled]),
      "/v1/patterns": () => json(200, { patterns: [] }),
      "GET patterns": () => json(200, { patterns: [] }),
      "/v1/ontology": () => json(200, ONTOLOGY),
      "GET rules/r1/runs": () => json(200, { rule_id: "r1", schedule: "every day at 06:00 (Europe/London)", state: "stopped",
        words: "Stopped after three refused runs in a row; the last: the rule's author, maker, can no longer sign in. Change the rule to start it again.",
        next_run: null, runs: [{ id: "x", rule_id: "r1", rule_version: 1, slot: "2026-11-02T06:00:00Z", ran_at: "2026-11-02T06:00:05Z",
          run_as: "maker", outcome: "refused", alerts: 0, words: "Refused: the rule's author, maker, can no longer sign in." }] }), // prettier-ignore
    });
    render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator={false} accountId="me" />);
    fireEvent.click(await screen.findByRole("button", { name: "Schedule and runs of Sanctioned people" }));
    const group = await screen.findByRole("group", { name: "The schedule of Sanctioned people" });
    expect(within(group).getByRole("status").textContent).toContain("Stopped after three refused runs in a row");
    expect(within(group).getByText(/refused — Refused: the rule's author, maker, can no longer sign in\./)).toBeTruthy();
  });
});

describe("maker–checker on a whole-deployment rule (decision 7)", () => {
  const pending = rule({ status: "pending", pending_action: "deploy", pending_by: "maker", pending_version: 1 });

  it("says a waiting rule does not run, and who proposed it", () => {
    expect(statusWords(pending)).toBe("not running: waiting for a second person's approval");
    expect(pendingWords(pending)).toBe("Waiting for a second person's approval: deploying it, proposed by maker.");
  });

  it("offers Approve and Reject to a second administrator-author, and sends each", async () => {
    let current = pending;
    const calls = serve({
      "GET rules": () => json(200, [current]),
      "GET patterns": () => json(200, { patterns: [] }),
      "/v1/ontology": () => json(200, ONTOLOGY),
      "POST rules/r1/approve": () => {
        current = rule({ status: "active" });
        return json(200, current);
      },
      "POST rules/r1/reject": () => json(200, rule({ status: "retired" })),
    });
    render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator accountId="checker" />);
    fireEvent.click(await screen.findByRole("button", { name: "Reject Sanctioned people" }));
    fireEvent.change(screen.getByLabelText("Why reject the change to Sanctioned people"), { target: { value: "too wide" } });
    fireEvent.click(screen.getByRole("button", { name: "Send the rejection of Sanctioned people" }));
    await waitFor(() => expect(calls.some((c) => c.path === "rules/r1/reject")).toBe(true));
    expect(calls.find((c) => c.path === "rules/r1/reject")!.body).toEqual({ reason: "too wide" });
    fireEvent.click(screen.getByRole("button", { name: "Approve Sanctioned people" }));
    await screen.findByText("Approved the change to “Sanctioned people”.");
  });

  it("offers the person who proposed it no Approve, and a non-administrator neither", async () => {
    serve({ "GET rules": () => json(200, [pending]), "GET patterns": () => json(200, { patterns: [] }), "/v1/ontology": () => json(200, ONTOLOGY) });
    const { unmount } = render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator accountId="maker" />);
    await screen.findByText(/proposed by maker/);
    expect(screen.queryByRole("button", { name: "Approve Sanctioned people" })).toBeNull();
    unmount();
    render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator={false} accountId="checker" />);
    await screen.findByText(/proposed by maker/);
    expect(screen.queryByRole("button", { name: "Approve Sanctioned people" })).toBeNull();
  });

  it("names who proposed it by their name, not their identity-provider id (step 9d finding 1)", async () => {
    const named = { ...pending, pending_by: "6f1c2a9e-idp-subject", pending_by_name: "Mo Maker" } as TypologyRule;
    serve({ "GET rules": () => json(200, [named]), "GET patterns": () => json(200, { patterns: [] }), "/v1/ontology": () => json(200, ONTOLOGY) });
    render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="author" isAdministrator accountId="checker" />);
    await screen.findByText("Waiting for a second person's approval: deploying it, proposed by Mo Maker.");
    expect(screen.queryByText(/6f1c2a9e-idp-subject/)).toBeNull();
  });

  it("shows the rule's versions with who made and who decided each", async () => {
    serve({
      "GET rules": () => json(200, [rule()]),
      "GET patterns": () => json(200, { patterns: [] }),
      "/v1/ontology": () => json(200, ONTOLOGY),
      "GET rules/r1/versions": () => json(200, [
        { rule_id: "r1", version: 1, action: "deploy", name: "x", params: {}, trigger: "post_commit", budget_ms: 5000,
          proposed_by: "maker", proposed_by_name: "Mo Maker", proposed_at: "2026-11-01T09:00:00Z", status: "approved",
          decided_by: "checker", decided_by_name: "Cath Checker", decided_at: "2026-11-01T10:00:00Z" },
      ]), // prettier-ignore
    });
    render(<RulesPanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="viewer" isAdministrator={false} accountId="v" />);
    fireEvent.click(await screen.findByRole("button", { name: "Versions of Sanctioned people" }));
    const list = await screen.findByRole("list", { name: "Versions of Sanctioned people" });
    expect(list.textContent).toMatch(/Version 1: deployed by Mo Maker .* · approved by Cath Checker/);
  });
});

describe("closing a high-severity alert (decision 7)", () => {
  const ALERT = { id: "a1", rule_id: "typology:r1", owner_id: "o", mode: "full", referent_node_ids: [], investigation_id: "c1",
    created_at: "2026-11-01T09:00:00Z", typology: "structuring", words: "4 movements", severity: "high", status: "claimed",
    assignee: "member" }; // prettier-ignore

  it("needs a second person where one may read it", () => {
    expect(closeNeedsSecondPerson("high", "case")).toBe(true);
    expect(closeNeedsSecondPerson("high", "owner")).toBe(false);
    expect(closeNeedsSecondPerson("medium", "team")).toBe(false);
    const closing = { ...ALERT, status: "closing", disposition: "false_positive", disposition_reason: "known", close_proposed_by: "member" };
    expect(statusSentence(closing as never, false)).toBe(
      "Closing as False positive (known), proposed by member: waiting for a second person to approve it",
    );
  });

  async function openAlert(alert: Record<string, unknown>, accountId: string) {
    const calls = serve({
      "GET alert-queue": () => json(200, [{ alert, summary: "4 movements", kind: "typology", severity: "high", audience: "case" }]),
      "GET alert-queue/a1": () => json(200, { alert, summary: "4 movements", nodes: [], edges: [], transactions: [], kind: "typology", severity: "high", audience: "case" }),
      "POST alert-queue/a1/disposition": () => json(200, { ...alert, status: "closing", close_proposed_by: accountId }),
      "POST alert-queue/a1/approve-close": () => json(200, { ...alert, status: "closed" }),
      "POST alert-queue/a1/send-back": () => json(200, { ...alert, status: "claimed" }),
      "GET alert-assignees": () => json(200, []),
    });
    render(<AlertQueue apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="editor" accountId={accountId} onCanvas={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Open alert:\s*High\s*severity/ }));
    return calls;
  }

  it("proposes the close and says it waits for a second person", async () => {
    const calls = await openAlert(ALERT, "member");
    await screen.findByText(/closing it here proposes the close/);
    fireEvent.change(screen.getByLabelText("Why, in words: the reason for closing"), { target: { value: "known" } });
    fireEvent.click(screen.getByRole("radio", { name: "False positive" }));
    fireEvent.click(screen.getByRole("button", { name: "Propose the close" }));
    await screen.findByText("Close proposed as False positive; it waits for a second person to approve it.");
    expect(calls.some((c) => c.path === "alert-queue/a1/disposition")).toBe(true);
  });

  it("names who proposed the close by their name on the approver's screen (step 9d finding 1)", async () => {
    const closing = { ...ALERT, status: "closing", disposition: "referred", disposition_reason: "to the regional unit",
      close_proposed_by: "6f1c2a9e-idp-subject" }; // prettier-ignore
    serve({
      "GET alert-queue": () => json(200, [{ alert: closing, summary: "4 movements", kind: "typology", severity: "high", audience: "case" }]),
      "GET alert-queue/a1": () => json(200, { alert: closing, summary: "4 movements", nodes: [], edges: [], transactions: [], kind: "typology",
        severity: "high", audience: "case", close_proposed_by_name: "Priya Shah" }), // prettier-ignore
      "GET alert-assignees": () => json(200, []),
    });
    render(<AlertQueue apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="editor" accountId="second" onCanvas={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Open alert:\s*High\s*severity/ }));
    const detail = await screen.findByRole("region", { name: "What fired this alert" });
    await within(detail).findByText(/proposed by Priya Shah: waiting for a second person/);
    expect(within(detail).queryByText(/6f1c2a9e-idp-subject/)).toBeNull();
  });

  it("names who claimed it by their name, in the queue and the detail (step 9e)", async () => {
    const claimed = { ...ALERT, severity: "medium", assignee: "6f1c2a9e-idp-subject" };
    serve({
      "GET alert-queue": () => json(200, [{ alert: claimed, summary: "4 movements", kind: "typology", severity: "medium", audience: "case",
        assignee_name: "Pat Jones" }]), // prettier-ignore
      "GET alert-queue/a1": () => json(200, { alert: claimed, summary: "4 movements", nodes: [], edges: [], transactions: [], kind: "typology",
        severity: "medium", audience: "case", assignee_name: "Pat Jones" }), // prettier-ignore
      "GET alert-assignees": () => json(200, []),
    });
    render(<AlertQueue apiBaseUrl="http://api" bearerToken="t" investigationId="c1" level="editor" accountId="second" onCanvas={vi.fn()} />);
    const queue = await screen.findByRole("region", { name: "Alert queue" });
    await within(queue).findByText(/Claimed · Pat Jones ·/);
    fireEvent.click(await screen.findByRole("button", { name: /Open alert:/ }));
    const detail = await screen.findByRole("region", { name: "What fired this alert" });
    await within(detail).findByText("Claimed by Pat Jones");
    expect(screen.queryByText(/6f1c2a9e-idp-subject/)).toBeNull();
  });

  it("names the approval group by its visible legend (A14, WCAG 2.5.3)", async () => {
    const closing = { ...ALERT, status: "closing", disposition: "false_positive", disposition_reason: "known", close_proposed_by: "member" };
    await openAlert(closing, "second");
    const group = await screen.findByRole("group", { name: "A second person decides this close" });
    expect(group.getAttribute("aria-label")).toBeNull();
  });

  it("says in words why the close button is not yet available, and stops once it is (A14)", async () => {
    await openAlert({ ...ALERT, severity: "medium" }, "member");
    const button = await screen.findByRole("button", { name: /^(Close the alert|Propose the close)$/ });
    const reason = () => {
      const id = button.getAttribute("aria-describedby");
      return id ? (document.getElementById(id)?.textContent ?? null) : null;
    };
    expect(button).toHaveProperty("disabled", true);
    expect(reason()).toBe("To close it, choose a closing reason and say why, in words.");
    expect(screen.getByText("To close it, choose a closing reason and say why, in words.")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "False positive" }));
    expect(reason()).toBe("To close it, say why, in words.");
    fireEvent.change(screen.getByLabelText(/the reason for closing$/), { target: { value: "a known supplier" } });
    expect(button).toHaveProperty("disabled", false);
    expect(reason()).toBeNull();
  });

  it("lets a second member approve or send back, and the proposer only withdraw", async () => {
    const closing = { ...ALERT, status: "closing", disposition: "false_positive", disposition_reason: "known", close_proposed_by: "member" };
    let calls = await openAlert(closing, "second");
    fireEvent.click(await screen.findByRole("button", { name: "Approve the close" }));
    await screen.findByText("Approved: the alert is closed.");
    expect(calls.some((c) => c.path === "alert-queue/a1/approve-close")).toBe(true);
    cleanup();
    calls = await openAlert(closing, "member");
    await screen.findByText(/You proposed this close/);
    expect(screen.queryByRole("button", { name: "Approve the close" })).toBeNull();
    fireEvent.change(screen.getByLabelText(/the reason for sending the close back$/), { target: { value: "on reflection" } });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw the close" }));
    await waitFor(() => expect(calls.find((c) => c.path === "alert-queue/a1/send-back")?.body).toEqual({ reason: "on reflection" }));
  });
});

describe("a screening list's refresh schedule (Amendment 3 item 4)", () => {
  const LIST = { list_name: "Synthetic list", source: "opensanctions", location: "lists/x.json", dataset: null, synthetic: true,
    licence: "CC BY-NC 4.0", version: "v1", entries: 10, updated_at: null, attempted_at: null, failure: null }; // prettier-ignore

  it("says the schedule in words, or that the list is refreshed by hand", () => {
    expect(scheduleState(LIST as never)).toBe("By hand only");
    expect(scheduleState({ ...LIST, schedule_words: "every day at 05:00 (Europe/London)" } as never)).toBe(
      "Refreshed every day at 05:00 (Europe/London)",
    );
  });

  it("sets a weekly schedule for whoever may load lists", async () => {
    const calls = serve({
      "GET /v1/admin/screening-lists": () => json(200, { lists: [LIST], updates: [], can_manage: true }),
      "PUT /v1/admin/screening-lists/Synthetic%20list/schedule": (body) =>
        json(200, { ...LIST, schedule: (body as { schedule: unknown }).schedule, schedule_words: "every Monday at 05:00 (Europe/London)" }),
    });
    render(<ListsPanel apiBaseUrl="http://api" bearerToken="t" canManage />);
    fireEvent.change(await screen.findByLabelText("Refreshed"), { target: { value: "weekly" } });
    fireEvent.change(screen.getByLabelText("On (refresh day)"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the schedule" }));
    await screen.findByText("“Synthetic list” is refreshed every Monday at 05:00 (Europe/London), as you.");
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ schedule: { every: "weekly", hour: 5, weekday: 1 } });
  });

  it("offers a reader no schedule to set", async () => {
    serve({ "GET /v1/screening-lists": () => json(200, { lists: [LIST], can_manage: false }) });
    render(<ListsPanel apiBaseUrl="http://api" bearerToken="t" canManage={false} />);
    await screen.findByText("By hand only");
    expect(screen.queryByRole("button", { name: "Save the schedule" })).toBeNull();
  });
});
