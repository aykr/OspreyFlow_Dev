// Admin › Audit (`06_DECISIONS.md` ADR-145 decision 10, O2; Amendment 3 decision 1; ADR-112 Amendment 7
// decision 7; ADR-146 Amendment 2): one view over the records the deployment keeps, read by the Conduit
// under your own principal (rule 3). Behind `read_audit`.
//
// Three records: the audit stream (the case audit, people, roles, datasets and loads), the rule audit
// of one case, and the engines' history. The Conduit decides what each entry may tell you: an entry
// about another unit's cases is never sent, and an entry's words are sent only where your own read of
// that record would show them; otherwise the row says they are withheld. Nothing here filters or hides
// what was sent: every filter is sent to the Conduit, which only narrows its read.
import { useEffect, useState } from "react";

import type { AuditSectionEntry, AuditSectionPage } from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import { readAudit, type AdminApi, type AuditQuery } from "../api";

const RECORDS: { value: AuditQuery["held_in"]; label: string }[] = [
  { value: "case_and_admin", label: "Cases, people, datasets and loads" },
  { value: "rules", label: "Rule audit of one case" },
  { value: "models", label: "Engines' history" },
];

const KINDS: { value: string; label: string }[] = [
  { value: "", label: "Every kind" },
  { value: "assertions", label: "Analyst assertions" },
  { value: "loads_and_promotions", label: "Loads and promotions" },
  { value: "types", label: "Types" },
  { value: "people_and_roles", label: "People and roles" },
  { value: "datasets", label: "Datasets" },
  { value: "reads_and_other", label: "Reads and refusals" },
];
const KIND_LABEL: Record<AuditSectionEntry["kind"], string> = {
  assertions: "Analyst assertion",
  loads_and_promotions: "Load or promotion",
  types: "Type",
  people_and_roles: "People and roles",
  datasets: "Dataset",
  rules: "Rule",
  models: "Engine",
  reads_and_other: "Read or refusal",
};

const PAGE = 50;

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/London" });

/** An action as words: `set_person_roles` reads "set person roles". */
export const actionWords = (action: string) => action.replace(/_/g, " ");

/** An entry's words as sent, or why there are none. */
export function entryWords(entry: AuditSectionEntry): string {
  if (entry.words_withheld || entry.detail == null) return "Withheld: your own read of this record would not show them";
  const parts = Object.entries(entry.detail)
    .filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  return parts.length ? parts.join("; ") : "—";
}

interface Form {
  held_in: AuditQuery["held_in"];
  kind: string;
  who: string;
  case: string;
  dataset: string;
  since: string;
  until: string;
}

const EMPTY: Form = { held_in: "case_and_admin", kind: "", who: "", case: "", dataset: "", since: "", until: "" };

/** The form as the Conduit's query: a date's day from midnight UTC; `until` takes the whole day. */
export function queryOf(form: Form, offset: number): AuditQuery {
  const day = (d: string, next: boolean) => {
    if (!d) return undefined;
    const t = new Date(`${d}T00:00:00Z`);
    if (next) t.setUTCDate(t.getUTCDate() + 1);
    return t.toISOString();
  };
  const stream = form.held_in === "case_and_admin";
  return {
    held_in: form.held_in,
    kind: stream ? form.kind || undefined : undefined,
    who: form.who || undefined,
    case: form.held_in !== "models" ? form.case.trim() || undefined : undefined,
    dataset: stream ? form.dataset.trim() || undefined : undefined,
    since: day(form.since, false),
    until: day(form.until, true),
    offset,
    limit: PAGE,
  };
}

export function Audit({ api }: { api: AdminApi }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [asked, setAsked] = useState<{ form: Form; offset: number } | null>({ form: EMPTY, offset: 0 });
  const [page, setPage] = useState<AuditSectionPage | null>(null);
  const [pageRecord, setPageRecord] = useState<AuditQuery["held_in"] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const set = (part: Partial<Form>) => setForm((f) => ({ ...f, ...part }));

  useEffect(() => {
    if (!asked) return;
    let live = true;
    setProblem(null);
    readAudit(api, queryOf(asked.form, asked.offset))
      .then((p) => {
        if (!live) return;
        setPage(p);
        setPageRecord(asked.form.held_in);
      })
      .catch((e: Error) => {
        if (!live) return;
        setPage(null);
        // A case not found is answered as one that does not exist (ADR-041): say so, nothing more.
        setProblem(/\(404\)/.test(e.message) ? "No case of yours by that id: it is not in your unit, or you may not read its rule audit." : e.message);
      });
    return () => {
      live = false;
    };
  }, [api, asked]);

  const rules = form.held_in === "rules";
  const stream = form.held_in === "case_and_admin";
  const show = () => {
    if (rules && !form.case.trim()) {
      setProblem("Choose the case whose rule audit to read: the rule audit is read for one case at a time.");
      return;
    }
    setAsked({ form, offset: 0 });
  };
  // The picker offers the people of the record last read, by name: the Conduit sends no account's
  // id (rule 7), and a name chosen here is sent back as the person filter.
  const people = page && pageRecord === form.held_in ? (page.people ?? []) : [];
  const offset = page?.offset ?? 0;
  // Only the named fields are read; a page missing its entries is read as none.
  const entries = page?.entries ?? [];
  const shownTo = offset + entries.length;

  return (
    <section aria-label="Audit" style={{ display: "grid", gap: "var(--sp-12)" }}>
      <p className="label" style={{ margin: 0 }}>
        Every audit this deployment keeps, read as you. Entries about another unit&apos;s cases are not shown, and an
        entry&apos;s words only where your own read of that record would show them.
      </p>
      <fieldset aria-label="Audit filters" style={{ display: "grid", gap: "var(--sp-8)", margin: 0 }}>
        <legend>Which entries</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "end" }}>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>Record</span>
            <Select value={form.held_in} onChange={(e) => set({ held_in: e.target.value as Form["held_in"], who: "" })}>
              {RECORDS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>
          </label>
          {stream && (
            <label style={{ display: "grid", gap: "var(--sp-4)" }}>
              <span>Kind</span>
              <Select value={form.kind} onChange={(e) => set({ kind: e.target.value })}>
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </Select>
            </label>
          )}
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>Person</span>
            <Select value={form.who} onChange={(e) => set({ who: e.target.value })}>
              <option value="">Anyone</option>
              {people.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          </label>
          {form.held_in !== "models" && (
            <label style={{ display: "grid", gap: "var(--sp-4)" }}>
              <span>{rules ? "Case (id, required)" : "Case (id)"}</span>
              <Input value={form.case} onChange={(e) => set({ case: e.target.value })} />
            </label>
          )}
          {stream && (
            <label style={{ display: "grid", gap: "var(--sp-4)" }}>
              <span>Dataset (id)</span>
              <Input value={form.dataset} onChange={(e) => set({ dataset: e.target.value })} />
            </label>
          )}
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>From</span>
            <Input type="date" value={form.since} onChange={(e) => set({ since: e.target.value })} />
          </label>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>To</span>
            <Input type="date" value={form.until} onChange={(e) => set({ until: e.target.value })} />
          </label>
          <Button onClick={show}>Show entries</Button>
        </div>
      </fieldset>
      {problem && <p role="alert">{problem}</p>}
      {!page && !problem && <p className="label">Reading…</p>}
      {page && (
        <>
          {page.note && (
            <p className="label" style={{ margin: 0 }}>
              {page.note}
            </p>
          )}
          <p role="status" style={{ margin: 0 }}>
            {!page.total
              ? "No entries you may read match these filters."
              : `Entries ${offset + 1}–${shownTo} of ${page.total}, newest first.`}
          </p>
          {entries.length > 0 && (
            <table className="table" aria-label="Audit entries">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Who</th>
                  <th scope="col">What</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Case</th>
                  <th scope="col">Words</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={`${e.recorded_at}-${i}`}>
                    <td>{when(e.recorded_at)}</td>
                    <td>{e.who}</td>
                    <td>{actionWords(e.action)}</td>
                    <td>{KIND_LABEL[e.kind]}</td>
                    <td>{e.case_name ?? "—"}</td>
                    <td>{entryWords(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {page.total > PAGE && asked && (
            <div style={{ display: "flex", gap: "var(--sp-8)" }}>
              <Button
                disabled={offset === 0}
                onClick={() => setAsked({ form: asked.form, offset: Math.max(0, offset - PAGE) })}
              >
                Newer entries
              </Button>
              <Button disabled={shownTo >= page.total} onClick={() => setAsked({ form: asked.form, offset: offset + PAGE })}>
                Older entries
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
