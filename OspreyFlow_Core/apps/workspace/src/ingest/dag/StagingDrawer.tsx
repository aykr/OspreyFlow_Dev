// A staging step's drawer (ADR-140 Amendment 12; Amendment 8's drawer beside the pipeline): its
// settings, as its record's own typed fields, and a live sample of its output over the first ten
// rows of each source, with the save gate's refusals in the gate's own words. Guided mode offers no
// expression anywhere (rule 8): every field is a table, a column, a list, a Knowledge Adapter's name,
// one of a closed set of choices, or a literal value; a Derive names an operation from its catalogue.
import { useEffect, useState } from "react";

import type { PipelineGraph, PipelineNode, StagingPreview } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { Table, type TableColumn } from "../../design/primitives/Table";
import { ProfileError, previewStaging } from "../api";
import { DERIVE_OPERATIONS, STAGING_KIND_NAMES, type StagingKind, tablesFor } from "./stagingSteps";

type Rec = Record<string, unknown>;
const text = (v: unknown): string => (typeof v === "string" ? v : v === undefined || v === null ? "" : String(v));
const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
/** A record without its empty optional parts, so the save gate judges what was set. */
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

const OPERATION_WORDS: Record<string, string> = {
  concat: "Join columns into one",
  split: "Take one part of a column",
  substring: "Take characters from a column",
  date_parse: "Read a date",
  arithmetic: "Add, subtract, multiply or divide",
  case_when: "Write a value for each value",
  normalise: "Normalise with a Knowledge Adapter",
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

function ColumnField({ label, value, columnsId, onChange }: { label: string; value: string; columnsId: string; onChange: (v: string) => void }) {
  return (
    <Field label={label}>
      <Input aria-label={label} value={value} list={columnsId} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

/** A list of rows, each a set of fields, with its own add and remove buttons named by what they do. */
function Rows<T>({
  noun,
  rows,
  make,
  onChange,
  render,
}: {
  noun: string;
  rows: T[];
  make: () => T;
  onChange: (rows: T[]) => void;
  render: (row: T, n: number, set: (row: T) => void) => React.ReactNode;
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

function AddedColumns({ value, columnsId, onChange }: { value: Rec[]; columnsId: string; onChange: (v: Rec[]) => void }) {
  return (
    <Rows<Rec>
      noun="Column to bring across"
      rows={value}
      make={() => ({ column: "" })}
      onChange={onChange}
      render={(row, n, set) => (
        <>
          <ColumnField label={`Column ${n}`} value={text(row.column)} columnsId={columnsId} onChange={(v) => set({ ...row, column: v })} />
          <Field label={`Name it (optional) ${n}`}>
            <Input aria-label={`Name it (optional) ${n}`} value={text(row.as)} onChange={(e) => set({ ...row, as: e.target.value })} />
          </Field>
        </>
      )}
    />
  );
}

function NameList({ noun, value, columnsId, onChange }: { noun: string; value: string[]; columnsId: string; onChange: (v: string[]) => void }) {
  return (
    <Rows<string>
      noun={noun}
      rows={value}
      make={() => ""}
      onChange={onChange}
      render={(row, n, set) => <ColumnField label={`${noun} ${n}`} value={row} columnsId={columnsId} onChange={set} />}
    />
  );
}

const FILTER_TESTS = [
  ["not_null", "has a value"],
  ["null", "is empty"],
  ["equals", "equals"],
  ["in", "is one of (separate values with |)"],
] as const;

function conditionTest(c: Rec): string {
  if (c.is === "null" || c.is === "not_null") return text(c.is);
  if (Array.isArray(c.in)) return "in";
  return "equals";
}

function DeriveSettings({ operation, value, onChange }: { operation: string; value: Rec; onChange: (v: Rec) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
  switch (operation) {
    case "concat":
      return (
        <Field label="Separator">
          <Input aria-label="Separator" value={text(value.separator ?? " ")} onChange={(e) => set("separator", e.target.value)} />
        </Field>
      );
    case "split":
      return (
        <>
          <Field label="Delimiter">
            <Input aria-label="Delimiter" value={text(value.delimiter ?? "|")} onChange={(e) => set("delimiter", e.target.value)} />
          </Field>
          <Field label="Part (0 is the first)">
            <Input aria-label="Part (0 is the first)" inputMode="numeric" value={text(value.part ?? 0)} onChange={(e) => set("part", num(e.target.value))} />
          </Field>
        </>
      );
    case "substring":
      return (
        <>
          <Field label="First character (0 is the first)">
            <Input aria-label="First character (0 is the first)" inputMode="numeric" value={text(value.start ?? 0)} onChange={(e) => set("start", num(e.target.value))} />
          </Field>
          <Field label="How many characters (optional)">
            <Input aria-label="How many characters (optional)" inputMode="numeric" value={text(value.length)} onChange={(e) => set("length", num(e.target.value))} />
          </Field>
        </>
      );
    case "date_parse":
      return (
        <>
          <Field label="Date order">
            <Select aria-label="Date order" value={text(value.date_order)} onChange={(e) => set("date_order", e.target.value || undefined)}>
              <option value="">ISO 8601 (year first)</option>
              <option value="dmy">Day, month, year</option>
              <option value="mdy">Month, day, year</option>
            </Select>
          </Field>
          <Field label="Time zone (optional)">
            <Input aria-label="Time zone (optional)" value={text(value.tz)} onChange={(e) => set("tz", e.target.value)} />
          </Field>
        </>
      );
    case "arithmetic":
      return (
        <>
          <Field label="Arithmetic">
            <Select aria-label="Arithmetic" value={text(value.op || "add")} onChange={(e) => set("op", e.target.value)}>
              <option value="add">Add</option>
              <option value="subtract">Subtract</option>
              <option value="multiply">Multiply</option>
              <option value="divide">Divide</option>
            </Select>
          </Field>
          <Field label="A number in place of a second column (optional)">
            <Input aria-label="A number in place of a second column (optional)" value={text(value.constant)} onChange={(e) => set("constant", e.target.value)} />
          </Field>
        </>
      );
    case "case_when":
      return (
        <>
          <Rows<Rec>
            noun="Case"
            rows={list<Rec>(value.cases)}
            make={() => ({ equals: "", then: "" })}
            onChange={(rows) => set("cases", rows)}
            render={(row, n, setRow) => (
              <>
                <Field label={`When the value is ${n}`}>
                  <Input aria-label={`When the value is ${n}`} value={text(row.equals)} onChange={(e) => setRow({ ...row, equals: e.target.value })} />
                </Field>
                <Field label={`Write ${n}`}>
                  <Input aria-label={`Write ${n}`} value={text(row.then)} onChange={(e) => setRow({ ...row, then: e.target.value })} />
                </Field>
              </>
            )}
          />
          <Field label="Otherwise (optional)">
            <Input aria-label="Otherwise (optional)" value={text(value.otherwise)} onChange={(e) => set("otherwise", e.target.value)} />
          </Field>
        </>
      );
    case "normalise":
      return (
        <Field label="Knowledge Adapter">
          <Input aria-label="Knowledge Adapter" value={text(value.adapter)} onChange={(e) => set("adapter", e.target.value)} />
        </Field>
      );
    default:
      return null;
  }
}

/** A drawer's settings for one step: edited here, applied with *Apply step settings*. */
export function StagingSettings({
  node,
  pipeline,
  busy,
  columns,
  onApply,
}: {
  node: PipelineNode;
  pipeline: PipelineGraph;
  busy: boolean;
  /** The columns the live sample last showed, offered as each column field's suggestions. */
  columns: string[];
  onApply: (config: Rec, label: string) => void;
}) {
  const kind = node.kind as StagingKind;
  const [rec, setRec] = useState<Rec>(node.config ?? {});
  const [label, setLabel] = useState(node.label);
  useEffect(() => {
    setRec(node.config ?? {});
    setLabel(node.label);
  }, [node]);
  const set = (k: string, v: unknown) => setRec((r) => ({ ...r, [k]: v }));
  const tables = tablesFor(pipeline, node.id);
  const columnsId = `columns-of-${node.id}`;

  return (
    <section aria-label={`${STAGING_KIND_NAMES[kind]} settings`} style={{ display: "grid", gap: "var(--sp-8)" }}>
      <datalist id={columnsId}>
        {columns.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <Field label="Step name">
        <Input aria-label="Step name" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      {kind === "lookup" && (
        <>
          <p className="label" style={{ margin: 0 }}>
            Adds columns from a reference list, matched on a key. Every row is kept; a row with no match keeps empty cells and is counted.
          </p>
          <TableChoice label="Reads" value={text(rec.input)} tables={tables} onChange={(v) => set("input", v)} />
          <Field label="Reference list">
            <Input aria-label="Reference list" value={text(rec.list)} onChange={(e) => set("list", e.target.value)} />
          </Field>
          <ColumnField label="Match on column" value={text(rec.on)} columnsId={columnsId} onChange={(v) => set("on", v)} />
          <Field label="Normalise the key with (optional)">
            <Input aria-label="Normalise the key with (optional)" value={text(rec.normalise)} onChange={(e) => set("normalise", e.target.value)} />
          </Field>
          <AddedColumns value={list<Rec>(rec.add)} columnsId={columnsId} onChange={(v) => set("add", v)} />
        </>
      )}
      {kind === "join" && (
        <>
          <p className="label" style={{ margin: 0 }}>
            Joins two tables on a declared key, never a guessed one. A row with several matches gives one row per match.
          </p>
          <TableChoice label="Left table" value={text(rec.left)} tables={tables} onChange={(v) => set("left", v)} />
          <TableChoice label="Right table" value={text(rec.right)} tables={tables} onChange={(v) => set("right", v)} />
          <ColumnField label="Left key column" value={text(rec.left_key)} columnsId={columnsId} onChange={(v) => set("left_key", v)} />
          <ColumnField label="Right key column" value={text(rec.right_key)} columnsId={columnsId} onChange={(v) => set("right_key", v)} />
          <Field label="Normalise both keys with (optional)">
            <Input aria-label="Normalise both keys with (optional)" value={text(rec.normalise)} onChange={(e) => set("normalise", e.target.value)} />
          </Field>
          <Field label="Keep">
            <Select aria-label="Keep" value={text(rec.how || "inner")} onChange={(e) => set("how", e.target.value)}>
              <option value="inner">Only left rows with a match</option>
              <option value="left">Every left row</option>
            </Select>
          </Field>
          <AddedColumns value={list<Rec>(rec.add)} columnsId={columnsId} onChange={(v) => set("add", v)} />
        </>
      )}
      {kind === "filter" && (
        <>
          <p className="label" style={{ margin: 0 }}>Keeps the rows for which every condition holds; the others are counted, not lost.</p>
          <TableChoice label="Reads" value={text(rec.input)} tables={tables} onChange={(v) => set("input", v)} />
          <Rows<Rec>
            noun="Condition"
            rows={list<Rec>(rec.keep)}
            make={() => ({ field: "", is: "not_null" })}
            onChange={(v) => set("keep", v)}
            render={(row, n, setRow) => {
              const test = conditionTest(row);
              const choose = (next: string) =>
                setRow(
                  next === "null" || next === "not_null"
                    ? { field: row.field, is: next }
                    : next === "in"
                      ? { field: row.field, in: [] }
                      : { field: row.field, equals: "" },
                );
              return (
                <>
                  <ColumnField label={`Column ${n}`} value={text(row.field)} columnsId={columnsId} onChange={(v) => setRow({ ...row, field: v })} />
                  <Field label={`Test ${n}`}>
                    <Select aria-label={`Test ${n}`} value={test} onChange={(e) => choose(e.target.value)}>
                      {FILTER_TESTS.map(([v, w]) => (
                        <option key={v} value={v}>
                          {w}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  {(test === "equals" || test === "in") && (
                    <Field label={`Value ${n}`}>
                      <Input
                        aria-label={`Value ${n}`}
                        value={test === "in" ? list<string>(row.in).join("|") : text(row.equals)}
                        onChange={(e) =>
                          setRow(
                            test === "in"
                              ? { field: row.field, in: e.target.value.split("|") }
                              : { field: row.field, equals: e.target.value },
                          )
                        }
                      />
                    </Field>
                  )}
                </>
              );
            }}
          />
        </>
      )}
      {kind === "derive" && (
        <>
          <p className="label" style={{ margin: 0 }}>Makes a new column with one operation from the catalogue. A row the operation cannot read is rejected with its cause.</p>
          <TableChoice label="Reads" value={text(rec.input)} tables={tables} onChange={(v) => set("input", v)} />
          <Field label="New column">
            <Input aria-label="New column" value={text(rec.column)} onChange={(e) => set("column", e.target.value)} />
          </Field>
          <Field label="Operation">
            <Select
              aria-label="Operation"
              value={text(rec.operation || "concat")}
              onChange={(e) => setRec((r) => ({ ...r, operation: e.target.value, settings: {} }))}
            >
              {DERIVE_OPERATIONS.map((op) => (
                <option key={op} value={op}>
                  {OPERATION_WORDS[op]}
                </option>
              ))}
            </Select>
          </Field>
          <NameList noun="Column it reads" value={list<string>(rec.columns)} columnsId={columnsId} onChange={(v) => set("columns", v)} />
          <DeriveSettings operation={text(rec.operation || "concat")} value={(rec.settings as Rec) ?? {}} onChange={(v) => set("settings", v)} />
        </>
      )}
      {kind === "union" && (
        <>
          <p className="label" style={{ margin: 0 }}>Stacks tables with the same columns; each row keeps where it came from.</p>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--sp-2)" }}>
            <legend className="label">Tables to stack</legend>
            {tables.map((t) => {
              const inputs = list<string>(rec.inputs);
              return (
                <label key={t} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={inputs.includes(t)}
                    onChange={(e) => set("inputs", e.target.checked ? [...inputs, t] : inputs.filter((x) => x !== t))}
                  />
                  {t}
                </label>
              );
            })}
          </fieldset>
        </>
      )}
      {kind === "dedupe" && (
        <>
          <p className="label" style={{ margin: 0 }}>Folds repeats: the first row stands for the others and carries where each came from.</p>
          <TableChoice label="Reads" value={text(rec.input)} tables={tables} onChange={(v) => set("input", v)} />
          <NameList noun="Same row when this column matches" value={list<string>(rec.on)} columnsId={columnsId} onChange={(v) => set("on", v)} />
        </>
      )}
      <div>
        <Button variant="primary" disabled={busy} onClick={() => onApply(prune(rec) as Rec, label.trim() || STAGING_KIND_NAMES[kind])}>
          Apply step settings
        </Button>
      </div>
    </section>
  );
}

function sampleWords(err: unknown): string {
  if (err instanceof ProfileError && err.code === "right_required")
    return "A step's sample reads the sources' rows, so it needs the right to edit pipelines, which you do not hold.";
  if (err instanceof ProfileError && err.code === "source_unreadable") return "A source could not be read. Check it is still where the source says.";
  return err instanceof Error ? err.message : "The sample could not be read.";
}

/** The live sample of a step's output: run as the drawer opens and after every change, writing
 * nothing; the save gate's refusals in its own words when it has any. */
export function StagingSample({
  apiBaseUrl,
  bearerToken,
  investigationId,
  recipeId,
  pipeline,
  step,
  onColumns,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  pipeline: PipelineGraph;
  step: string;
  onColumns?: (columns: string[]) => void;
}) {
  const [preview, setPreview] = useState<StagingPreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const key = JSON.stringify(pipeline);

  async function run() {
    setBusy(true);
    setProblem(null);
    try {
      const found = await previewStaging(apiBaseUrl, bearerToken, investigationId, recipeId, pipeline, step);
      setPreview(found);
      if (found.columns?.length) onColumns?.(found.columns);
    } catch (err: unknown) {
      setProblem(sampleWords(err));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void run();
    // `key` stands for the pipeline: a sample follows every change the drawer applies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, step]);

  const columnNames = preview?.columns ?? [];
  const rows = (preview?.rows ?? []).map((values, i) => ({ i, values }));
  const tableColumns: TableColumn<{ i: number; values: Record<string, string> }>[] = [
    { key: "#", header: "Row", numeric: true, render: (r) => String(r.i + 1) },
    ...columnNames.map((name) => ({ key: name, header: name, render: (r: { i: number; values: Record<string, string> }) => r.values[name] ?? "" })),
  ];
  const problems = preview?.problems ?? [];
  return (
    <section aria-label="Sample of this step" style={{ display: "grid", gap: "var(--sp-8)", minWidth: 0 }}>
      <h4 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Sample</h4>
      <p className="label" style={{ margin: 0 }}>
        The steps up to this one over the first ten rows of each source, at your own clearance. Nothing is written.
      </p>
      <div>
        <Button disabled={busy} onClick={() => void run()}>
          {busy ? "Reading the sample…" : "Read the sample again"}
        </Button>
      </div>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {problems.length > 0 && (
        <div role="alert" aria-label="What the save gate refuses" style={{ display: "grid", gap: "var(--sp-2)" }}>
          <p style={{ margin: 0 }}>The save gate refuses this pipeline:</p>
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {preview && problems.length === 0 && (
        <>
          <p role="status" style={{ margin: 0 }}>
            {`${rows.length} row${rows.length === 1 ? "" : "s"} out, from ${preview.rows_sampled} source row${preview.rows_sampled === 1 ? "" : "s"} read.`}
            {preview.values_masked && " Some values are masked to their shape: you are not cleared for every row's marking."}
          </p>
          <div style={{ overflowX: "auto" }} tabIndex={0} role="region" aria-label="Sample rows">
            <Table columns={tableColumns} rows={rows} getRowId={(r) => String(r.i)} />
          </div>
          <ul aria-label="Each step's counts" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {(preview.counts ?? []).map((c) => (
              <li key={c.step}>
                {`${c.step}: ${c.rows_in} in, ${c.rows_out} out`}
                {c.unmatched ? `, ${c.unmatched} with no match` : ""}
                {c.filtered_out ? `, ${c.filtered_out} left out` : ""}
                {c.repeats_folded ? `, ${c.repeats_folded} repeats folded` : ""}
                {c.rejected ? `, ${c.rejected} rejected` : ""}
                {c.right_rows_in ? `; right table ${c.right_rows_in} in, ${c.right_unmatched ?? 0} met no left row` : ""}
              </li>
            ))}
          </ul>
          {(preview.rejections ?? []).length > 0 && (
            <ul aria-label="Rows refused" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {(preview.rejections ?? []).map((r, i) => (
                <li key={i}>{r.reason}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
