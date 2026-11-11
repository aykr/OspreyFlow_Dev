// The Admin area's keyboard harness (ADR-110 Amendment 1, ADR-112, `CLAUDE.md` rule 13): its own
// surface, its own registry (`ADMIN_ACTIONS`). Every call is intercepted by `admin.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AdminPlace } from "../src/admin/AdminPlace";
import { applyHarnessBrand } from "./brandHarness";

// `?brand=govuk` (ADR-145 decision 13): the side list as a GOV.UK side navigation, scanned so.
await applyHarnessBrand();

const tab = new URLSearchParams(location.search).get("rights") ?? "manage_people,manage_dashboards,administer_system";
const open = new URLSearchParams(location.search).get("open");

// `?open=connections` (ADR-140 Amendment 4): for the every-harness axe scan, the page serves the
// Connections section's list itself and opens the section. `?open=<section label>` otherwise opens
// that section from the side list (ADR-145 decision 5), for the scan of a placeholder. Synthetic (rule 9). Without it, `admin.spec.ts`
// intercepts every call as before.
if (open === "connections") {
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    const body =
      path === "/v1/admin/connections"
        ? [
            { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "2026-11-01T00:00:00Z" },
            { id: "c2", kind: "files", name: "Second folder", created_by: "admin-1", created_at: "2026-11-05T00:00:00Z" },
          ]
        : [];
    return new Response(JSON.stringify(body), { status: 200 });
  };
}

// `?serve=datasets` (L2.4 part 2): for the axe scans, the page serves Admin › Datasets and System
// itself: a dataset with its Authors (one approver, so the warning shows) and linked cases, one
// removed; `show=` then opens a dataset's details (`details`), Change owner… (`owner`) or a dry run
// (`dry-run`). Synthetic (rule 9).
const serving = new URLSearchParams(location.search).get("serve");
const show = new URLSearchParams(location.search).get("show");
if (serving === "datasets") {
  const DATASET = { id: "ds-a", name: "Prison records", owning_unit: "unit-1", egress: "none", kind: "source",
                    highest_marking: null, promotion_policy: "second_person_reviews" };  // prettier-ignore
  const served: Record<string, unknown> = {
    "/v1/admin/datasets": [DATASET, { ...DATASET, id: "ds-d", name: "Drawn: Op Heron", kind: "drawn", highest_marking: "OFFICIAL" }],
    "/v1/admin/datasets/ds-a/authors": { dataset_id: "ds-a", has_home_case: true, team: null,
      people: [{ id: "eng-1", name: "D. Engineer", approves: true }, { id: "adm-2", name: "S. Lead", approves: false }] },
    "/v1/admin/datasets/ds-a/cases": { dataset_id: "ds-a", cases: [
      { investigation_id: "home-a", name: "Prison records", state: "open", home_case: true, through: null, items: 0, links: 0, size_bytes: 0 },
      { investigation_id: "open-1", name: "Op Kestrel", state: "open", home_case: false, through: null, items: 3, links: 2, size_bytes: 700 },
      { investigation_id: "gone-1", name: "Op Heron", state: "removed", home_case: false, through: null, items: 5, links: 4, size_bytes: 50000 },
      { investigation_id: "via-1", name: "Op Merlin", state: "removed", home_case: false, through: "Both", items: 1, links: 0, size_bytes: 90 },
    ] },
    // L2.5c: `show=delete`, the delete's dry run shown with Admin's own Delete after it.
    "/v1/admin/datasets/ds-a/cases/gone-1/delete/dry-run": { investigation_id: "gone-1", action: "delete", items: 5,
      links: 4, size_bytes: 50000,
      would: "Op Heron's layer holds 5 items and 4 links (48.8 kB). Deleting it withdraws those not promoted; promoted items are never touched. Nothing has been written." },
    "/v1/admin/datasets/ds-a/cases/gone-1/merge/dry-run": { investigation_id: "gone-1", action: "merge", items: 5, links: 4,
      size_bytes: 50000, would: "Would merge 5 items and 4 links (48.8 kB) from Op Heron's layer into Prison records. Nothing has been written." },
    "/v1/admin/settings/dataset-owners": { owners_may_be: "people_and_teams" },
    "/v1/admin/system": { components: [{ name: "Graph store", ok: true, millis: 12 }],
      converted_views: { views: 3, cases: 2 } },
  };  // prettier-ignore
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    return new Response(JSON.stringify(served[path] ?? []), { status: 200 });
  };
}

// `?serve=people` (L2.5): for the axe scans, the page serves Admin › People and Roles itself: two
// people, one holding a team's custom role, their case levels, a case with no Author, the roles and a
// disable plan; `show=` then opens *Disable…* (`disable`), a new role's form (`role-form`) or a team
// (`team`). Synthetic (rule 9).
if (serving === "people") {
  const ANA = { id: "u1", username: "ana", name: "Ana Analyst", enabled: true, roles: ["analyst", "role:r1"],
                clearance: "OFFICIAL", org_unit: "unit-1" };  // prettier-ignore
  const TEAM = { role_id: "r1", display_name: "Intel", mailbox: "intel@example.org", lead: "u1", cover: "u2",
                 cover_until: "2026-11-14", acting_lead: "u2",
                 members: [{ id: "u1", name: "Ana Analyst" }, { id: "u2", name: "Bea Engineer" }] };  // prettier-ignore
  const served: Record<string, unknown> = {
    "/v1/admin/people": [ANA, { ...ANA, id: "u2", username: "bea", name: "Bea Engineer", roles: ["data_engineer", "role:r1"] }],
    "/v1/admin/organisation-arrivals": [],
    "/v1/admin/people/rows": {
      rows: [{ id: "u1", levels: [{ investigation_id: "c1", name: "Op Kestrel", level: "author", through: null },
                                  { investigation_id: "c2", name: "Op Heron", level: "editor", through: "Intel" }] }],
      without_author: [{ investigation_id: "c3", name: "Op Wren" }],
    },
    "/v1/admin/roles": {
      built_in: [
        { id: "analyst", label: "Analyst", rights: ["investigate", "triage_alerts", "promote_to_dataset"], gives: [] },
        { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "review_promotions"], gives: [] },
        { id: "osprey-admin", label: "Admin", rights: ["administer_system", "manage_people"], gives: [] },
        { id: "super_user", label: "Super user", rights: ["investigate", "edit_pipelines", "author_rules"],
          gives: ["analyst", "data_engineer", "rule_author"] },
      ],
      custom: [{ id: "r1", name: "Intel desk", version: 2, rights: ["investigate", "read_reports"], changed_by: "adm-1",
                 changed_at: "2026-11-08T09:00:00Z", holders: 2, team: TEAM }],
    },
    "/v1/admin/people/u1/disable-plan": { person: "u1",
      not_yet_listed: ["promotions waiting for review", "reviews waiting on them"],
      items: [{ kind: "case_author", id: "c1", label: "Only Author of the case Op Kestrel" },
              { kind: "view", id: "v1", investigation_id: "c1", label: "A private view of the case Op Kestrel" },
              { kind: "drawn_watch", id: "w1", investigation_id: "c1",
                label: "A watch on an item they drew in the case Op Kestrel" },
              { kind: "team_lead", id: "r1", label: "Lead of the team Intel" },
              { kind: "typology_rule", id: "t1", label: "The rule Structuring, whose runs act as them" }] },
    "/v1/handling-scheme": { classification: ["OFFICIAL", "SECRET"], handling_codes: { P: {} } },
    // L2.5b: `show=withheld`, the person also owns items this administrator may not see.
    "/v1/admin/people/u1/ownership": { person: "u1", items: [], counts: {}, withheld: show === "withheld",
      not_yet_listed: [] },
    "/v1/admin/roles/r1/versions": [
      { version: 1, name: "Intel desk", rights: ["investigate"], changed_by: "adm-1", changed_at: "2026-11-07T09:00:00Z" },
      { version: 2, name: "Intel desk", rights: ["investigate", "read_reports"], changed_by: "adm-1", changed_at: "2026-11-08T09:00:00Z" },
    ],
  };  // prettier-ignore
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    // `show=refused`: the plan refused in words, as for a person who owns another unit's case.
    if (show === "refused" && path === "/v1/admin/people/u1/disable-plan")
      return new Response(JSON.stringify({ detail: { error: "other_unit", message:
        "they answer for 1 cases, rules or pipeline schedules of another unit: that unit's administrator transfers those first" } }), { status: 409 });  // prettier-ignore
    return new Response(JSON.stringify(served[path] ?? []), { status: 200 });
  };
}
// `?serve=audit` (L2.6): for the axe scans, the page serves Admin › Audit itself: a page of the stream
// with one entry's words withheld and one's shown, more than a page in all (so its paging shows); and
// `?serve=operations`, Operations' ageing with an overdue promotion waiting, and a schedule. `show=rules`
// then chooses the rule audit and asks without a case, so its refusal shows. Synthetic (rule 9).
if (serving === "audit" || serving === "operations") {
  const ENTRY = { recorded_at: "2026-11-08T09:00:00Z", who: "Ana Analyst",
                  action: "confirm_node", kind: "assertions", held_in: "case_and_admin", investigation_id: "c1",
                  case_name: "Op Kestrel", detail: null, words_withheld: true, result_cardinality: null };  // prettier-ignore
  const served: Record<string, unknown> = {
    "/v1/admin/audit": { total: 120, offset: 0, limit: 50, people: ["Ana Analyst", "Bea Analyst"],
      note: "Entries about another unit's cases are not shown. Entries written before 8 November 2026 that name no case recorded no unit, so they are not shown either. The rule audit is read for one case at a time: choose Rule audit of one case.",
      entries: [ENTRY, { ...ENTRY, action: "set_person_roles", kind: "people_and_roles", investigation_id: null, case_name: null,
                         detail: { person: "Bea Analyst", roles: ["analyst"] }, words_withheld: false, result_cardinality: 1 }] },
    "/v1/admin/operations/ageing": { alert_after_days: 3, promotions_recorded: true,
      rules: [{ what: "A promotion waiting for review", after_days: 3,
                then: "After 3 days it is flagged overdue, and the dataset's Authors who may review it and the unit's administrators are alerted once. The alert names the load and the dataset, not what it adds." }],
      waiting: [{ promotion_id: "p1", load_id: "load-7", dataset_id: "ds-a", dataset_name: "Prison records", proposed_by_name: "Ana Analyst",
                  proposed_at: "2026-11-01T09:00:00Z", age_days: 7, overdue: true }] },
    "/v1/admin/schedules": [{ recipe_id: "feed", label: "Daily custody export", case_id: "case-1", cron: "0 6 * * 1-5",
      timezone: "Europe/London", schedule: "every weekday at 06:00 (Europe/London)", owner: "approver-1",
      next_run: "2026-11-09T06:00:00Z", paused: false, paused_reason: null, flagged: false, last_run: null }],
  };  // prettier-ignore
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    return new Response(JSON.stringify(served[path] ?? []), { status: 200 });
  };
}
// `?serve=policies` (L2.7): Admin › Policies › Grading scheme, read-only, over the scheme the page serves;
// `?serve=connections`: Connections with an API connection bound to a dataset, and `show=sql` draws the
// form's SQL fields. Synthetic (rule 9).
if (serving === "policies" || serving === "connections") {
  const served: Record<string, unknown> = {
    "/v1/grading-scheme": { scheme: "admiralty", source: ["A", "B", "C", "D", "E", "F"], intelligence: ["1", "2", "3", "4", "5", "6"],
                            handling: ["P", "C"] },
    "/v1/admin/connections": [
      { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "2026-11-01T00:00:00Z" },
      { id: "c-api", kind: "api", name: "Telco lookup (synthetic)", created_by: "admin-1", created_at: "2026-11-05T00:00:00Z",
        datasets: ["ds-a"], settings: { kind: "api", base_url: "https://telco.example", auth: "bearer", secret: "TELCO", pagination: "none" } },
      // L1.9: an S3 bucket and Athena, each read as the deployment's own cloud role (no secret's name).
      { id: "c-s3", kind: "s3", name: "Client exports (synthetic)", created_by: "admin-1", created_at: "2026-11-11T00:00:00Z",
        datasets: ["ds-a"], settings: { kind: "s3", region: "eu-west-2", bucket: "synthetic-exports", prefix: "client-a/" } },
      { id: "c-athena", kind: "athena", name: "Client Athena (synthetic)", created_by: "admin-1", created_at: "2026-11-11T00:00:00Z",
        datasets: ["ds-a"], settings: { kind: "athena", region: "eu-west-2", workgroup: "primary", databases: ["visits"] } },
    ],
    "/v1/admin/datasets": [{ id: "ds-a", name: "Prison records", owning_unit: "u", egress: "none", kind: "source",
                             promotion_policy: "author_promotes" }],
  };  // prettier-ignore
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    return new Response(JSON.stringify(served[path] ?? []), { status: 200 });
  };
}
createRoot(document.getElementById("root")!).render(
  <AdminPlace apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" rights={new Set(tab.split(","))} />,
);

if (open) {
  const label = open === "connections" ? "Connections" : open;
  for (let i = 0; i < 40; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("nav[aria-label='Admin sections'] button")].find(
      (b) => b.textContent === label,
    );
    if (button) {
      button.click();
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

/** Presses the button named `name` once it is drawn, for the scans' opened states. */
async function pressWhenDrawn(name: string) {
  for (let i = 0; i < 60; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
      (b) => (b.getAttribute("aria-label") ?? b.textContent) === name,
    );
    if (button) {
      button.click();
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

if (serving === "datasets" && show) {
  await pressWhenDrawn("Details for Prison records");
  if (show === "owner") await pressWhenDrawn("Change owner of Prison records");
  if (show === "dry-run") await pressWhenDrawn("Merge Op Heron into the dataset (dry run)");
  if (show === "delete") await pressWhenDrawn("Delete Op Heron's layer (dry run)");
}
if (serving === "people" && show) {
  if (show === "disable" || show === "refused" || show === "withheld") await pressWhenDrawn("Disable ana");
  if (show === "versions") await pressWhenDrawn("Versions of Intel desk");
  if (show === "role-form") await pressWhenDrawn("Copy Analyst into a new role");
  if (show === "team") await pressWhenDrawn("Team for Intel desk");
}
if (serving === "audit" && show === "rules") {
  for (let i = 0; i < 60 && !document.querySelector("table[aria-label='Audit entries']"); i++)
    await new Promise((resolve) => setTimeout(resolve, 50));
  const record = [...document.querySelectorAll<HTMLSelectElement>("select")].find((el) =>
    [...el.options].some((o) => o.value === "rules"),
  );
  if (record) {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(record, "rules");
    record.dispatchEvent(new Event("change", { bubbles: true }));
  }
  await pressWhenDrawn("Show entries");
}
// `show=sql`, `show=s3` or `show=athena` (L1.9) draws that kind's fields.
if (serving === "connections" && (show === "sql" || show === "s3" || show === "athena")) {
  for (let i = 0; i < 60 && !document.querySelector("table[aria-label='Connections of this deployment']"); i++)
    await new Promise((resolve) => setTimeout(resolve, 50));
  const kind = [...document.querySelectorAll<HTMLSelectElement>("select")].find((el) => [...el.options].some((o) => o.value === "sql"));
  if (kind) {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(kind, show);
    kind.dispatchEvent(new Event("change", { bubbles: true }));
  }
}
