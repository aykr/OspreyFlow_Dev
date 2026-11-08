// The expert steps' drawers (ADR-140 decisions 3, 12 and 13; the redesign's phase 8; brief §5.3–5.4).
// A SQL transform: the tables it reads, its one SELECT, and the plain-words summary every run report
// and guided mode show beside it; *Check SQL* asks the sandbox's gate before it is applied. A fuzzy
// match: the two tables, the comparisons (the Splink-backed methods the product has), optional
// blocking keys, the threshold (part of the version), the columns it brings across and the two
// elements of Map's template its SAME_AS joins, inferred and never a merge. Offered in expert mode to
// a holder of `write_sql_transforms` only; everyone else reads the step whole, read-only
// (`ExpertStepReadOnly`), and the server refuses a change without the right in any case.
import { useState } from "react";

import type { ExpertStepDisclosure, PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Checkbox } from "../../design/primitives/Checkbox";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { checkSql } from "../api";
import { FUZZY_BLOCKS, FUZZY_METHODS, STAGING_KIND_NAMES, tablesFor, type ExpertKind } from "./stagingSteps";

type Rec = Record<string, unknown>;
const text = (v: unknown): string => (typeof v === "string" ? v : v === undefined || v === null ? "" : String(v));
const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

const METHOD_WORDS: Record<string, string> = {
  jaro_winkler: "Name similarity (Jaro-Winkler)",
  levenshtein: "Spelling distance (Levenshtein)",
  exact: "Exactly the same",
};
const BLOCK_WORDS: Record<string, string> = {
  exact: "the same value",
  soundex: "the same sound (Soundex)",
  year: "the same year",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "grid", gap: "var(--sp-2)" }}>
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

function TableChoice({ label, value, tables, onChange }: { label: string; value: string; tables: string[]; onChange: (v: string) => void }) {
  return (
    <Field label={label}>
      <Select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose a table</option>
        {tables.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/** Rows of fields with their own add and remove buttons, named by what they do. */
function Rows({
  noun,
  rows,
  make,
  onChange,
  render,
}: {
  noun: string;
  rows: Rec[];
  make: () => Rec;
  onChange: (rows: Rec[]) => void;
  render: (row: Rec, n: number, set: (row: Rec) => void) => React.ReactNode;
}) {
  return (
    <div role="group" aria-label={`${noun}s`} style={{ display: "grid", gap: "var(--sp-4)" }}>
      {rows.map((row, i) => (
        <div key={i} style={{ display: "flex", gap: "var(--sp-4)", alignItems: "end", flexWrap: "wrap" }}>
          {render(row, i + 1, (next) => onChange(rows.map((r, j) => (j === i ? next : r))))}
          <Button onClick={() => onChange(rows.filter((_, j) => j !== i))}>{`Remove ${noun.toLowerCase()} ${i + 1}`}</Button>
        </div>
      ))}
      <div>
        <Button onClick={() => onChange([...rows, make()])}>{`+ ${noun}`}</Button>
      </div>
    </div>
  );
}

function prune(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(prune);
  if (value && typeof value === "object") {
    const out: Rec = {};
    for (const [k, v] of Object.entries(value as Rec)) {
      const kept = prune(v);
      if (kept === "" || kept === null || kept === undefined) continue;
      out[k] = kept;
    }
    return out;
  }
  return value;
}

export interface ExpertSettingsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  node: PipelineNode;
  pipeline: PipelineGraph;
  busy: boolean;
  columns: string[];
  onApply: (config: Rec, label: string) => void;
}

/** An expert step's own settings, applied with *Apply step settings*. */
export function ExpertSettings(props: ExpertSettingsProps) {
  const { node, pipeline, busy, columns, onApply } = props;
  const kind = node.kind as ExpertKind;
  const [rec, setRec] = useState<Rec>(node.config ?? {});
  const [label, setLabel] = useState(node.label);
  // The threshold as typed ("0." on the way to "0.6"), read as a number when applied.
  const [threshold, setThreshold] = useState(text(node.config?.threshold));
  const [checked, setChecked] = useState<string[] | null>(null);
  const [checking, setChecking] = useState(false);
  const set = (k: string, v: unknown) => setRec((r) => ({ ...r, [k]: v }));
  const tables = tablesFor(pipeline, node.id);
  const columnsId = `columns-of-${node.id}`;
  const entities = (pipeline.nodes ?? []).some((n) => n.kind === "map");

  async function check() {
    setChecking(true);
    try {
      const held = { ...pipeline, nodes: (pipeline.nodes ?? []).map((n) => (n.id === node.id ? { ...n, config: prune(rec) as Rec } : n)) };
      setChecked(await checkSql(props.apiBaseUrl, props.bearerToken, props.investigationId, props.recipeId, held, node.id));
    } catch (err: unknown) {
      setChecked([err instanceof Error ? err.message : "The SQL could not be checked."]);
    } finally {
      setChecking(false);
    }
  }

  return (
    <section aria-label={`${STAGING_KIND_NAMES[kind]} settings`} style={{ display: "grid", gap: "var(--sp-8)" }}>
      <datalist id={columnsId}>
        {columns.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <p className="label" style={{ margin: 0 }}>
        An expert step: it needs the right to write SQL transforms, and every run report and Test disclose it.
      </p>
      <Field label="Step name">
        <Input aria-label="Step name" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      {kind === "sql" && (
        <>
          <p className="label" style={{ margin: 0 }}>
            One SELECT over the tables it reads, run in a sandbox: no files, no network, no other table, only the rows you
            may read. Carry each table&apos;s <code>_ref</code> column through (an aggregate as <code>list(_ref)</code>), so
            every row names the rows it came from.
          </p>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--sp-2)" }}>
            <legend className="label">Tables it reads</legend>
            {tables.map((t) => {
              const inputs = list<string>(rec.inputs);
              return (
                <label key={t} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", minHeight: 24 }}>
                  <Checkbox
                    checked={inputs.includes(t)}
                    onChange={(e) => set("inputs", e.target.checked ? [...inputs, t] : inputs.filter((x) => x !== t))}
                  />
                  {t}
                </label>
              );
            })}
          </fieldset>
          <Field label="SELECT">
            <textarea
              className="input"
              aria-label="SELECT"
              rows={8}
              spellCheck={false}
              style={{ fontFamily: "var(--font-mono)", minWidth: 0 }}
              value={text(rec.select)}
              onChange={(e) => set("select", e.target.value)}
            />
          </Field>
          <Field label="What it does, in plain words">
            <textarea
              className="input"
              aria-label="What it does, in plain words"
              rows={2}
              maxLength={500}
              value={text(rec.summary)}
              onChange={(e) => set("summary", e.target.value)}
            />
          </Field>
          <div>
            <Button disabled={checking} onClick={() => void check()}>
              {checking ? "Checking the SQL…" : "Check SQL"}
            </Button>
          </div>
          {checked !== null &&
            (checked.length === 0 ? (
              <p role="status" style={{ margin: 0 }}>
                The sandbox&apos;s gate accepts this SELECT.
              </p>
            ) : (
              <div role="alert" aria-label="What the sandbox refuses" style={{ display: "grid", gap: "var(--sp-2)" }}>
                <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
                  {checked.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            ))}
        </>
      )}
      {kind === "fuzzy_match" && (
        <>
          <p className="label" style={{ margin: 0 }}>
            Compares each left row with the right table&apos;s rows. Every left row is kept; one scoring at least the threshold
            takes the columns you bring across and its score. What Map writes from them is inferred, and the match is an
            inferred SAME_AS between two records, never a merge. A row below the threshold is kept and counted.
          </p>
          <TableChoice label="Left table" value={text(rec.left)} tables={tables} onChange={(v) => set("left", v)} />
          <TableChoice label="Right table" value={text(rec.right)} tables={tables} onChange={(v) => set("right", v)} />
          <Rows
            noun="Comparison"
            rows={list<Rec>(rec.compare)}
            make={() => ({ left: "", right: "", method: "jaro_winkler" })}
            onChange={(v) => set("compare", v)}
            render={(row, n, setRow) => (
              <>
                <Field label={`Left column ${n}`}>
                  <Input aria-label={`Left column ${n}`} list={columnsId} value={text(row.left)} onChange={(e) => setRow({ ...row, left: e.target.value })} />
                </Field>
                <Field label={`Right column ${n}`}>
                  <Input aria-label={`Right column ${n}`} value={text(row.right)} onChange={(e) => setRow({ ...row, right: e.target.value })} />
                </Field>
                <Field label={`Compared by ${n}`}>
                  <Select aria-label={`Compared by ${n}`} value={text(row.method || "jaro_winkler")} onChange={(e) => setRow({ ...row, method: e.target.value })}>
                    {FUZZY_METHODS.map((m) => (
                      <option key={m} value={m}>
                        {METHOD_WORDS[m]}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}
          />
          <Rows
            noun="Blocking key"
            rows={list<Rec>(rec.block_on)}
            make={() => ({ left: "", right: "", method: "exact" })}
            onChange={(v) => set("block_on", v)}
            render={(row, n, setRow) => (
              <>
                <Field label={`Left key column ${n}`}>
                  <Input aria-label={`Left key column ${n}`} list={columnsId} value={text(row.left)} onChange={(e) => setRow({ ...row, left: e.target.value })} />
                </Field>
                <Field label={`Right key column ${n}`}>
                  <Input aria-label={`Right key column ${n}`} value={text(row.right)} onChange={(e) => setRow({ ...row, right: e.target.value })} />
                </Field>
                <Field label={`Pairs agree on ${n}`}>
                  <Select aria-label={`Pairs agree on ${n}`} value={text(row.method || "exact")} onChange={(e) => setRow({ ...row, method: e.target.value })}>
                    {FUZZY_BLOCKS.map((m) => (
                      <option key={m} value={m}>
                        {BLOCK_WORDS[m]}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}
          />
          <Field label="Threshold (between 0 and 1; part of the version)">
            <Input
              aria-label="Threshold (between 0 and 1; part of the version)"
              inputMode="decimal"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </Field>
          <Rows
            noun="Column to bring across"
            rows={list<Rec>(rec.add)}
            make={() => ({ column: "" })}
            onChange={(v) => set("add", v)}
            render={(row, n, setRow) => (
              <>
                <Field label={`Right column to bring ${n}`}>
                  <Input aria-label={`Right column to bring ${n}`} value={text(row.column)} onChange={(e) => setRow({ ...row, column: e.target.value })} />
                </Field>
                <Field label={`Name it (optional) ${n}`}>
                  <Input aria-label={`Name it (optional) ${n}`} value={text(row.as)} onChange={(e) => setRow({ ...row, as: e.target.value })} />
                </Field>
              </>
            )}
          />
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--sp-4)" }}>
            <legend className="label">The SAME_AS it writes, between two elements of Map&apos;s template</legend>
            <Field label="The left row's element">
              <Input
                aria-label="The left row's element"
                value={text((rec.same_as as Rec | undefined)?.left)}
                onChange={(e) => set("same_as", { ...((rec.same_as as Rec) ?? {}), left: e.target.value })}
              />
            </Field>
            <Field label="The matched row's element">
              <Input
                aria-label="The matched row's element"
                value={text((rec.same_as as Rec | undefined)?.right)}
                onChange={(e) => set("same_as", { ...((rec.same_as as Rec) ?? {}), right: e.target.value })}
              />
            </Field>
            {!entities && <p className="label" style={{ margin: 0 }}>Name them once Map has its elements.</p>}
          </fieldset>
        </>
      )}
      <div>
        <Button
          variant="primary"
          disabled={busy}
          onClick={() => {
            // A threshold that is not a number is sent as written, for the gate to refuse in words.
            const typed = threshold.trim();
            const withThreshold = kind === "fuzzy_match" ? { ...rec, threshold: typed === "" ? undefined : Number.isNaN(Number(typed)) ? typed : Number(typed) } : rec;
            onApply(prune(withThreshold) as Rec, label.trim() || STAGING_KIND_NAMES[kind]);
          }}
        >
          Apply step settings
        </Button>
      </div>
    </section>
  );
}

/** What a disclosure says, in words: as every run report and Test say it. */
export function disclosureWords(d: ExpertStepDisclosure): string[] {
  const name = d.label ?? d.step;
  if (d.kind === "sql")
    return [
      `${name} (SQL transform, reads ${(d.reads ?? []).join(" and ")}): ${d.summary ?? ""}`,
    ];
  return [
    `${name} (fuzzy match of ${(d.reads ?? []).join(" against ")}, threshold ${d.threshold}): ${(d.compares ?? []).join("; ")}.`,
    `It writes an inferred SAME_AS between ${(d.same_as ?? []).join(" and ")}, never a merge; a person confirms it.`,
  ];
}

/** ADR-140 decision 16: the expert steps a run or a Test ran, disclosed in every report. */
export function ExpertDisclosure({
  steps,
  title = "Expert steps in this run",
}: {
  steps: readonly ExpertStepDisclosure[] | undefined;
  title?: string;
}) {
  if (!steps || steps.length === 0) return null;
  return (
    <section aria-label={title} style={{ display: "grid", gap: "var(--sp-4)" }}>
      <h4 style={{ margin: 0, fontSize: "var(--fs-13)" }}>{title}</h4>
      <ul style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" }}>
        {steps.map((d) => (
          <li key={d.step}>
            {disclosureWords(d).map((w) => (
              <div key={w}>{w}</div>
            ))}
            {d.select && (
              <pre className="value" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "var(--font-mono)" }}>
                {d.select}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A pipeline's expert steps as the run report discloses them, from its own nodes (the Runs tab's
 * grid reads runs, not reports). */
export function disclosuresOf(pipeline: PipelineGraph | null | undefined): ExpertStepDisclosure[] {
  return (pipeline?.nodes ?? [])
    .filter((n) => n.kind === "sql" || n.kind === "fuzzy_match")
    .map((n) => {
      const c = (n.config ?? {}) as Rec;
      if (n.kind === "sql")
        return { step: n.id, kind: "sql", label: n.label, summary: text(c.summary), select: text(c.select), reads: list<string>(c.inputs) };
      return {
        step: n.id,
        kind: "fuzzy_match",
        label: n.label,
        reads: [text(c.left), text(c.right)],
        compares: list<Rec>(c.compare).map((x) => `${text(x.left)} ≈ ${text(x.right)} by ${text(x.method)}`),
        threshold: typeof c.threshold === "number" ? c.threshold : null,
        same_as: [text((c.same_as as Rec | undefined)?.left), text((c.same_as as Rec | undefined)?.right)],
      };
    });
}

/** An expert step for anyone the drawer does not offer its editor to: read whole, never hidden
 * (ADR-140 decision 3). */
export function ExpertStepReadOnly({ node, why }: { node: PipelineNode; why: string }) {
  const [disclosure] = disclosuresOf({ nodes: [node], edges: [] });
  return (
    <section aria-label="Expert step" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <p className="label" style={{ margin: 0 }}>
        {why}
      </p>
      {disclosure && <ExpertDisclosure steps={[disclosure]} title="What this step does" />}
    </section>
  );
}
