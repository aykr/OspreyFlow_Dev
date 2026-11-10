// The Ingest Studio harness's staging steps (ADR-140 Amendment 12): the "Visits and contacts" draft
// (`?contacts=1`), what its staging preview answers, and the save gate's refusals the keyboard walk
// meets, in the gate's own words (`services/ingest/pipeline.staging_graph_violations` and
// `staging_catalogue.staging_rule_violations`), so the fake refuses those as the route refuses them
// (rule 15), not only what it grants. It does not model every refusal: not a Derive's `normalise`,
// a step named like a source, a step reading itself or a later one, an undeclared key, nor the
// preview's withholding from a reader not cleared for every sampled row. Those are the server's,
// proved in `test_studio_staging_routes.py` and `test_staging_pipeline_nodes.py`. The rows are the exit fixture's (`tests/ingest/fixtures/visits_and_contacts`):
// synthetic, Ofcom drama numbers and invented names (rule 9). The engine here is a small stand-in for
// the server's, enough to give each step a sample to read; the server's own is what the Python tests
// prove.
import FIXTURE from "./fixtures/visits_and_contacts_pipeline.json";

type Row = Record<string, string>;
type Node = { id: string; kind: string; label: string; config?: Record<string, unknown> };
type Graph = { nodes: Node[]; edges: { source: string; target: string }[] };

const VISIT_BOOKINGS: Row[] = [
  ["VB-2605-001", "FMR", "WHITLOW", "Shona", "07700 900731", "2026-11-01T09:12:00+00:00", "Tue 4 Nov 14:00"],
  ["VB-2605-002", "HBK", "ELLERY", "Mark", "+44 7700 900719", "2026-11-01T10:40:00+00:00", "Wed 5 Nov 10:00"],
  ["VB-2605-003", "FMR", "OKAFOR", "Ada", "07700900720", "2026-11-02T08:05:00+00:00", "Thu 6 Nov 15:30"],
  ["VB-2605-004", "HBK", "PRICE", "Tom", "not given", "2026-11-02T11:20:00+00:00", "Thu 6 Nov 10:00"],
  ["VB-2605-005", "XXX", "LANE", "Jo", "07700 900731", "2026-11-03T16:45:00+00:00", "Fri 7 Nov 14:00"],
  ["VB-2605-006", "FMR", "BELL", "Iris", "07700 900722", "yesterday", "Sat 8 Nov 11:00"],
].map(([booking_id, estab_id, visitor_family_name, visitor_given_names, contact_number, booked_at, visit_at]) => ({
  booking_id: booking_id!, estab_id: estab_id!, visitor_family_name: visitor_family_name!,
  visitor_given_names: visitor_given_names!, contact_number: contact_number!, booked_at: booked_at!, visit_at: visit_at!,
}));  // prettier-ignore
const NUMBER_OWNERS: Row[] = [
  { number: "+447700900731", owner_family_name: "WHITLOW", since: "2025-04-01" },
  { number: "07700 900719", owner_family_name: "ELLERY", since: "2024-01-12" },
  { number: "0770 0900 721", owner_family_name: "ODE", since: "2023-03-03" },
  { number: "unknown", owner_family_name: "NOBODY", since: "2020-01-01" },
];
const ESTABLISHMENTS: Row[] = [
  { estab_id: "FMR", name: "HMP Fenwick Moor", region: "North" },
  { estab_id: "HBK", name: "HMP Halbeck", region: "Midlands" },
];
const SOURCES: Record<string, Row[]> = { visit_bookings: VISIT_BOOKINGS, number_owners: NUMBER_OWNERS };
/** The lists this dataset reads (its live model names them, their rows kept). */
const LISTS: Record<string, { key: string; rows: Row[] }> = { establishments: { key: "estab_id", rows: ESTABLISHMENTS } };
/** One-column text adapters the gate admits (`derive.text_adapters`), the ones this walk names. */
const TEXT_ADAPTERS = new Set(["msisdn", "prison_number", "upper", "lower", "trim"]);

export const CONTACTS_DRAFT = (base: Record<string, unknown>, created_at: string) => ({
  ...base, recipe_id: "r-contacts", version: 1, status: "draft", label: "Visits and contacts",
  source_location: "harbour-extract/visit_bookings.csv", handling: { classification: "OFFICIAL" },
  pipeline: FIXTURE.base, created_at, verified_at: null,
});  // prettier-ignore

export const CONTACTS_PROFILE = {
  rows_sampled: VISIT_BOOKINGS.length, sample_is_whole_source: true, values_masked: false,
  columns: Object.keys(VISIT_BOOKINGS[0]!).map((name) => ({ name, sample_size: 6, null_count: 0, distinct_count: 6, inferred_type: "string", type_confidence: 1 })),
};  // prettier-ignore
export const CONTACTS_SAMPLE_ROWS = VISIT_BOOKINGS;

const STAGING = new Set(["lookup", "join", "filter", "derive", "union", "dedupe", "sql", "fuzzy_match"]);
/** Phase 8's expert steps: the harness judges their records and the sandbox's gate as the Conduit's
 * words say them, but runs neither (no DuckDB or Splink in the browser); their samples are the route
 * tests' (`tests/services/api/test_studio_expert_routes.py`). */
export const EXPERT = new Set(["sql", "fuzzy_match"]);
const text = (v: unknown) => (typeof v === "string" ? v : "");
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
function inputsOf(n: Node): string[] {
  const c = n.config ?? {};
  if (n.kind === "join" || n.kind === "fuzzy_match") return [text(c.left), text(c.right)];
  if (n.kind === "union" || n.kind === "sql") return arr<string>(c.inputs);
  return [text(c.input)];
}

/** `sql_transform.sql_gate_problems`' refusals, in its words, for the shapes the walks meet: a
 * table function, a second statement, a SELECT dropping `_ref` (rule 15: the fake refuses). */
export function sqlGateProblems(id: string, select: string, inputs: string[]): string[] {
  const statements = select.split(";").filter((part) => part.trim()).length;
  if (statements !== 1)
    return [`step '${id}' is one SELECT statement, not ${statements}: a SQL step runs a single SELECT and nothing else`];
  if (!/^\s*(with|select)\b/i.test(select)) return [`step '${id}''s statement is not a SELECT: a SQL step reads its tables and changes nothing`];
  const problems: string[] = [];
  for (const m of select.matchAll(/\b(read_\w+|query|range|glob)\s*\(/gi))
    problems.push(`step '${id}' reads through a table function (${m[1]!.toLowerCase()}), which a SQL step may not: it reads only the tables named in its inputs`);
  for (const m of select.matchAll(/\b(?:from|join)\s+([A-Za-z_][\w.]*)/gi))
    if (!inputs.includes(m[1]!) && !/^\(/.test(m[1]!))
      problems.push(`step '${id}' reads '${m[1]}', which is not one of the tables it reads (${inputs.join(", ")})`);
  if (!/_ref\b|\*/.test(select))
    problems.push(`step '${id}''s SELECT drops the _ref column: carry each input row's _ref through (an aggregate as list(_ref)), so every row it gives names the rows it came from`);
  return [...new Set(problems)];
}

/** What a step's record lacks, in the gate's words (`pipeline._record_problems`). */
function recordProblems(n: Node): string[] {
  const c = n.config ?? {};
  const needs = (keys: string[]) => keys.filter((k) => !text(c[k])).map((k) => `step '${n.id}' needs '${k}'`);
  const least = (key: string, min: number) => (arr(c[key]).length < min ? [`step '${n.id}' needs at least ${min} in '${key}'`] : []);
  switch (n.kind) {
    case "lookup":
      return [...needs(["input", "list", "on"]), ...least("add", 1)];
    case "join":
      return [...needs(["left", "right", "left_key", "right_key"]), ...least("add", 1)];
    case "filter":
      return [...needs(["input"]), ...least("keep", 1)];
    case "derive": {
      const out = [...needs(["input", "column"]), ...least("columns", 1)];
      if (!out.length && c.operation === "concat" && arr(c.columns).length < 2)
        out.push(`step '${n.id}': concat reads at least 2 column(s), not ${arr(c.columns).length}`);
      return out;
    }
    case "union":
      return least("inputs", 2);
    case "dedupe":
      return [...needs(["input"]), ...least("on", 1)];
    case "sql":
      return [...least("inputs", 1), ...needs(["select", "summary"])];
    case "fuzzy_match": {
      const out = [...needs(["left", "right"]), ...least("compare", 1), ...least("add", 1)];
      const same = (c.same_as ?? {}) as Record<string, unknown>;
      if (!text(same.left) || !text(same.right)) out.push(`step '${n.id}' needs 'same_as'`);
      return out;
    }
    default:
      return [];
  }
}

function order(graph: Graph): Node[] {
  const steps = graph.nodes.filter((n) => STAGING.has(n.kind));
  const ids = new Set(steps.map((s) => s.id));
  const out: Node[] = [];
  const placed = new Set<string>();
  let pending = [...steps];
  while (pending.length) {
    const ready = pending.find((s) => inputsOf(s).every((t) => placed.has(t) || !ids.has(t)));
    if (!ready) return [...out, ...pending];
    out.push(ready);
    placed.add(ready.id);
    pending = pending.filter((s) => s !== ready);
  }
  return out;
}

/** Every refusal of the graph's steps, in the gate's words; empty when there are none. */
export function stagingRefusals(graph: Graph): string[] {
  const steps = graph.nodes.filter((n) => STAGING.has(n.kind));
  if (!steps.length) return [];
  const records = steps.flatMap(recordProblems);
  if (records.length) return records;
  const problems: string[] = [];
  const edges = new Set(graph.edges.map((e) => `${e.source}→${e.target}`));
  for (const s of steps)
    for (const t of inputsOf(s)) if (!edges.has(`${t}→${s.id}`)) problems.push(`step '${s.id}' reads '${t}', but no line joins them on the pipeline`);
  const ordered = order(graph);
  const last = ordered.at(-1)!;
  const maps = graph.nodes.filter((n) => n.kind === "map").map((n) => n.id);
  if (!maps.some((m) => edges.has(`${last.id}→${m}`))) problems.push(`the last step, '${last.id}', feeds no Map: Map reads the last step's table`);
  const read = new Set(steps.flatMap(inputsOf));
  for (const n of graph.nodes)
    if (n.kind === "source" && !read.has(n.id))
      problems.push(`source '${n.label}' is read by no step: a pipeline with staging steps maps only its last step's table, so its rows would go nowhere`);
  const labelOf = new Map(graph.nodes.map((n) => [n.id, n.label]));
  const kindOf = new Map(graph.nodes.map((n) => [n.id, n.kind]));
  for (const e of [...graph.edges].sort((a, b) => (a.source + a.target).localeCompare(b.source + b.target)))
    if (maps.includes(e.target) && e.source !== last.id && ["source", "profile", ...STAGING].includes(kindOf.get(e.source) ?? ""))
      problems.push(`'${labelOf.get(e.source) ?? e.source}' feeds Map, but Map reads only the last step's table`);
  if (problems.length) return problems;
  const known = graph.nodes.filter((n) => n.kind === "source").map((n) => n.id);
  const readLater = new Set<string>();
  for (const s of ordered) {
    for (const t of inputsOf(s)) {
      if (!known.includes(t)) problems.push(`step '${s.id}' reads '${t}', which is neither a source table of this pipeline nor an earlier step`);
      readLater.add(t);
    }
    const c = s.config ?? {};
    if (s.kind === "lookup" && !LISTS[text(c.list)])
      problems.push(`step '${s.id}' looks up '${text(c.list)}', which names no list this dataset holds or subscribes to`);
    if ((s.kind === "lookup" || s.kind === "join") && c.normalise && !TEXT_ADAPTERS.has(text(c.normalise)))
      problems.push(`step '${s.id}' normalises its key with '${text(c.normalise)}', which is not a Knowledge Adapter that reads one column into one value of text`);
    if (s.kind === "sql") problems.push(...sqlGateProblems(s.id, text(c.select), inputsOf(s)));
    if (s.kind === "fuzzy_match" && s !== ordered.at(-1))
      problems.push(`step '${s.id}' is a fuzzy match, which is the last step: Map reads its matched columns, and writes what it binds from them as inferred`);
    known.push(s.id);
  }
  for (const s of ordered.slice(0, -1))
    if (!readLater.has(s.id)) problems.push(`step '${s.id}' feeds nothing: every step but the last must feed a later one (the last is what Map reads)`);
  return problems;
}

type Refused = { reason: string; refs: { table: string; row_index: number; side?: string }[] };
type Done = { columns: string[]; rows: Row[]; count: Record<string, unknown>; refused: Refused[] };

function msisdn(v: string): string | null {
  if (/[a-z]/i.test(v)) return null;
  const digits = v.replace(/\D/g, "");
  return digits.startsWith("0") ? `+44${digits.slice(1)}` : `+${digits}`;
}

function key(v: string, normalise: string): string | null | undefined {
  if (!v.trim()) return undefined;
  return normalise === "msisdn" ? msisdn(v) : v.trim();
}

function runStep(s: Node, tables: Record<string, { columns: string[]; rows: Row[] }>): Done {
  const c = s.config ?? {};
  const add = arr<{ column: string; as?: string }>(c.add);
  const count = { step: s.id, kind: s.kind, rows_in: 0, rows_out: 0 } as Record<string, number | string>;
  const refused: Refused[] = [];
  if (s.kind === "lookup") {
    const input = tables[text(c.input)]!;
    const list = LISTS[text(c.list)]!;
    const columns = [...input.columns, ...add.map((a) => a.as || a.column)];
    let unmatched = 0;
    const rows = input.rows.map((r) => {
      const hit = list.rows.find((l) => l[list.key] === r[text(c.on)]);
      if (!hit) unmatched++;
      return { ...r, ...Object.fromEntries(add.map((a) => [a.as || a.column, hit?.[a.column] ?? ""])) };
    });
    return { columns, rows, count: { ...count, rows_in: input.rows.length, rows_out: rows.length, unmatched }, refused };
  }
  if (s.kind === "join") {
    const left = tables[text(c.left)]!;
    const right = tables[text(c.right)]!;
    const norm = text(c.normalise);
    const rightKeys = right.rows.map((r, i) => {
      const k = key(r[text(c.right_key)] ?? "", norm);
      if (k === null) refused.push({ reason: `staging step ${s.id} (right side, ${text(c.right)} row ${i}): ${text(c.right_key)}: a phone number has no letters in it`, refs: [{ table: text(c.right), row_index: i, side: "right" }] });
      return k;
    });
    const columns = [...left.columns, ...add.map((a) => a.as || a.column)];
    const rows: Row[] = [];
    let unmatched = 0;
    const met = new Set<number>();
    left.rows.forEach((r, i) => {
      const k = key(r[text(c.left_key)] ?? "", norm);
      if (k === null) {
        refused.push({ reason: `staging step ${s.id} (left side, ${text(c.left)} row ${i}): ${text(c.left_key)}: a phone number has no letters in it`, refs: [{ table: text(c.left), row_index: i, side: "left" }] });
        return;
      }
      const hits = rightKeys.flatMap((rk, j) => (k && rk === k ? [j] : []));
      hits.forEach((j) => met.add(j));
      if (!hits.length) {
        unmatched++;
        if (c.how === "left") rows.push({ ...r, ...Object.fromEntries(add.map((a) => [a.as || a.column, ""])) });
      }
      for (const j of hits) rows.push({ ...r, ...Object.fromEntries(add.map((a) => [a.as || a.column, right.rows[j]![a.column] ?? ""])) });
    });
    const rightRejected = rightKeys.filter((k) => k === null).length;
    return { columns, rows, refused, count: { ...count, rows_in: left.rows.length, rows_out: rows.length, unmatched,
      rejected: refused.length, right_rows_in: right.rows.length, right_unmatched: right.rows.length - met.size - rightRejected } };  // prettier-ignore
  }
  if (s.kind === "derive") {
    const input = tables[text(c.input)]!;
    const settings = (c.settings as Record<string, unknown>) ?? {};
    const sep = typeof settings.separator === "string" ? settings.separator : " ";
    const columns = [...input.columns, text(c.column)];
    const rows = input.rows.map((r) => ({ ...r, [text(c.column)]: arr<string>(c.columns).map((col) => r[col] ?? "").filter(Boolean).join(sep) }));
    return { columns, rows, refused, count: { ...count, rows_in: input.rows.length, rows_out: rows.length } };
  }
  if (s.kind === "filter") {
    const input = tables[text(c.input)]!;
    const holds = (r: Row) =>
      arr<Record<string, unknown>>(c.keep).every((k) => {
        const v = (r[text(k.field)] ?? "").trim();
        if (k.is === "null") return !v;
        if (k.is === "not_null") return Boolean(v);
        if (Array.isArray(k.in)) return (k.in as string[]).map((x) => x.trim()).includes(v);
        return v === text(k.equals).trim();
      });
    const rows = input.rows.filter(holds);
    return { columns: input.columns, rows, refused, count: { ...count, rows_in: input.rows.length, rows_out: rows.length, filtered_out: input.rows.length - rows.length } };
  }
  if (s.kind === "union") {
    const inputs = arr<string>(c.inputs).map((t) => tables[t]!);
    const rows = inputs.flatMap((t) => t.rows);
    return { columns: inputs[0]!.columns, rows, refused, count: { ...count, rows_in: rows.length, rows_out: rows.length } };
  }
  const input = tables[text(c.input)]!;
  const seen = new Set<string>();
  const rows = input.rows.filter((r) => {
    const k = JSON.stringify(arr<string>(c.on).map((col) => r[col] ?? ""));
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return { columns: input.columns, rows, refused, count: { ...count, rows_in: input.rows.length, rows_out: rows.length, repeats_folded: input.rows.length - rows.length } };
}

/** `POST …/staging-preview`, as the route answers it (`studio_staging.preview_staging`). */
export function stagingPreview(graph: Graph, step: string, pipelineProblems: string[]) {
  const problems = [...pipelineProblems, ...stagingRefusals(graph).filter((p) => !pipelineProblems.includes(p))];
  const empty = { step, problems, columns: [], rows: [], values_masked: false, rows_sampled: 0, counts: [], rejections: [] };
  // As the route: a record refused by its schema runs nothing; any other refusal is reported beside
  // the sample of the steps this one needs, when they can run.
  const steps = graph.nodes.filter((n) => STAGING.has(n.kind));
  if (steps.some((n) => recordProblems(n).length)) return empty;
  const needed = new Set<string>();
  const want = [step];
  while (want.length) {
    const at = want.pop()!;
    const node = steps.find((n) => n.id === at);
    if (!node || needed.has(at)) continue;
    needed.add(at);
    want.push(...inputsOf(node));
  }
  const runnable = order(graph).filter((n) => needed.has(n.id));
  if (runnable.some((n) => EXPERT.has(n.kind))) return { ...empty, problems };
  if (runnable.some((n) => problems.some((p) => p.startsWith(`step '${n.id}'`)))) return empty;
  const ordered = runnable;
  if (!ordered.some((s) => s.id === step)) return { step, problems: [`the pipeline has no step '${step}' to preview`] };
  const tables: Record<string, { columns: string[]; rows: Row[] }> = Object.fromEntries(
    Object.entries(SOURCES).map(([name, rows]) => [name, { columns: Object.keys(rows[0]!), rows }]),
  );
  const counts: Record<string, unknown>[] = [];
  const rejections: { row_index: number; reason: string; sample: string; refs: Refused["refs"] }[] = [];
  let out: Done | null = null;
  for (const s of ordered) {
    out = runStep(s, tables);
    tables[s.id] = { columns: out.columns, rows: out.rows };
    counts.push(out.count);
    rejections.push(...out.refused.map((r) => ({ row_index: r.refs[0]!.row_index, reason: r.reason, sample: "", refs: r.refs })));
    if (s.id === step) break;
  }
  const table = tables[step]!;
  const profile = table.rows.length
    ? { rows_sampled: table.rows.length, sample_is_whole_source: true, values_masked: false,
        columns: table.columns.map((name) => ({ name, sample_size: table.rows.length, null_count: table.rows.filter((r) => !r[name]).length,
          distinct_count: new Set(table.rows.map((r) => r[name])).size, inferred_type: "string", type_confidence: 1,
          sample_values: [...new Set(table.rows.map((r) => r[name]).filter(Boolean))].slice(0, 5) })) }  // prettier-ignore
    : null;
  return { step, problems, columns: table.columns, rows: table.rows, values_masked: false,
    rows_sampled: VISIT_BOOKINGS.length + NUMBER_OWNERS.length, counts, rejections, profile };  // prettier-ignore
}

/** The exit's pipeline with its three steps set, as the keys build it. */
export const CONTACTS_BUILT = FIXTURE.pipeline;

/** The step ids `FIXTURE.pipeline` holds, with each one's record: what the exit walk builds. */
export const EXIT_STEPS = FIXTURE.pipeline.nodes.filter((n) => STAGING.has(n.kind));
