/**
 * The dataset map's words and the plain logic its table is made from (slice IS3; ADR-140 Amendment 22 items 1 and 8;
 * ADR-141 Amendment 2). The page is a read-only table of the pipelines that load one dataset: pipeline, status, version and
 * stages. Nothing here is a page or a call: a word, or a function from what the Conduit answered to the table's rows, so each
 * is a test's to read.
 *
 * The order pipelines run in (slice IS6a; the owner's rulings of 24 November 2026): a "Runs after" column is drawn only once an
 * order is stored (the owner's ruling of 21 November 2026: never an empty column, and nothing the order does not back), an
 * undeployed pipeline in it is said "not deployed", and a plain form sets the order. The page never says what the order should
 * be, and draws no line between two pipelines. `tests/glass_trees/test_dataset_map_scenario.py` fails on such words here and in
 * the template.
 *
 * Why the stage and status words are written out again here: they are the Studio's own (`ingest/dag/PipelineCanvas.tsx`'s
 * `KIND_NAMES` and `ingest/studio/vocabulary.ts`'s `STATUS_WORDS`, in the workspace, which a server file cannot import). The
 * same test holds each pair to the screen's, so a word changed there is red here.
 *
 * The stage order is the canvas's layout (`ingest/dag/pipelineLayout.ts`): a stage sits in a column by the longest path from
 * a stage that nothing feeds, and in a row by its place in the graph's own list. That layout is written once more below
 * (about twenty lines) because this table needs the order and not the drawing; `test/server/datasetMapLayout.test.ts` runs both
 * on the same graphs.
 */
import { whenWords } from "./modelWords.js";
import { isDeployed, refusalWords } from "./studioWords.js";
import type { Pipeline } from "./studioWords.js";

/** The Studio's words for a stage kind (`PipelineCanvas.tsx`, `KIND_NAMES`). A kind this build does not know is shown as stored. */
export const KIND_NAMES: Record<string, string> = {
  domain_model: "Domain model",
  source: "Source",
  profile: "Profile",
  map: "Map",
  extract: "Extract",
  enrich: "Enrich",
  load: "Load",
  lookup: "Lookup",
  join: "Join",
  filter: "Filter",
  derive: "Derive",
  union: "Union",
  dedupe: "Dedupe",
  sql: "SQL transform",
  fuzzy_match: "Fuzzy match",
};

/** The Studio's words for a pipeline's status (`vocabulary.ts`, `STATUS_WORDS`). A status this build does not know is shown as stored. */
export const STATUS_WORDS: Record<string, string> = {
  draft: "draft",
  published: "deployed",
  flagged: "needs attention",
  superseded: "previous version",
};

export const DATASET_MAP_WORDS = {
  title: "Ingest Studio · Dataset map",
  heading: "Dataset map",
  intro: "Every pipeline that loads this dataset maps into its domain model, which is on 1 Model.",
  caption: (datasetName: string) => `Pipelines loading ${datasetName}`,
  columns: ["Pipeline", "Status", "Version", "Stages"] as const,
  /** The same columns and one more: drawn only when an order is stored. */
  columnsWithOrder: ["Pipeline", "Status", "Version", "Stages", "Runs after"] as const,
  sorted: "Sorted by pipeline name.",
  /** What a pipeline that is not deployed is called wherever the order names it. */
  notDeployed: "not deployed",
  runsAfterNothing: "Nothing",
  orderHeading: "Run order",
  orderIntro:
    "Choose, for each pipeline, the pipelines it runs after. The order is stored with the dataset, and saving it runs nothing. A pipeline that is not deployed can be in the order; it is not run until it is deployed.",
  orderLine: (version: number, by: string | null, when: string | null) =>
    `Run order version ${version}${by === null ? "" : `, saved by ${by}`}${when === null ? "" : ` on ${when}`}.`,
  legend: (name: string) => `${name} runs after`,
  save: "Save the run order",
  saved: (version: number) => `The run order is saved as version ${version}.`,
  /** A read of the stored order that did not work: said, never drawn as an order that was never stored. */
  orderUnreadable:
    "The run order of this dataset could not be read just now, so it is not shown and cannot be changed. Try again in a few minutes.",
  saveFailed: "The run order could not be saved just now. Nothing has changed. Try again in a few minutes.",
  notUnderstood: "That request was not understood. Nothing has changed.",
  otherDataset: "That form was for another dataset. Nothing has changed. Open the dataset map again.",
  /** The Conduit's own words for a refusal of an order, when it gave them; these are for when it did not. */
  refusedOrder: (status: number) => `The run order was refused (${status}). Nothing has changed.`,
  /** Said before the Conduit's own words when the order moved on since the page was read: what was ticked is kept. */
  movedOn: "The run order was changed by someone else since you read it, so nothing was saved. It is shown as it is now, with your choices ticked.",
  empty: "No pipeline loads this dataset yet.",
  unreadable: "The pipelines of this dataset could not be read just now. Try again in a few minutes.",
  /**
   * One sentence for every reason the map is not drawn for a person: they lack the right to read the pipelines, the Conduit no
   * longer opens the case, no case of theirs loads into the dataset, or there is no such dataset. The Conduit answers a thing a
   * person may not see exactly as one that does not exist, and so does this page (rule 3: no oracle).
   */
  refused: refusalWords(403, undefined, "The dataset map"),
  unnamed: "Unnamed pipeline",
  notRecorded: "Not recorded",
} as const;

// -------------------------------------------------------------------------------------------------- the stages

type Graph = NonNullable<Pipeline["pipeline"]>;

/** The ids of a graph's stages in the order the canvas lays them out: by column, then by place in the graph's own list. */
export function stageIds(graph: Graph): string[] {
  const nodes = graph.nodes ?? [];
  const feeders = new Map<string, string[]>();
  for (const edge of graph.edges ?? []) feeders.set(edge.target, [...(feeders.get(edge.target) ?? []), edge.source]);
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (id: string): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    // A cycle never reaches a saved graph (it is refused at save), but a page must not hang on one.
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const above = (feeders.get(id) ?? []).map(depthOf);
    const found = above.length === 0 ? 0 : Math.max(...above) + 1;
    visiting.delete(id);
    depth.set(id, found);
    return found;
  };
  return nodes
    .map((node, place) => ({ id: node.id, column: depthOf(node.id), place }))
    .sort((a, b) => a.column - b.column || a.place - b.place)
    .map((placed) => placed.id);
}

/** A pipeline's stages as words, in layout order, or `null` when it is kept without a graph. */
export function stageWords(graph: Pipeline["pipeline"]): string | null {
  if (!graph || !Array.isArray(graph.nodes) || graph.nodes.length === 0) return null;
  const kinds = new Map(graph.nodes.map((node) => [node.id, node.kind]));
  return stageIds(graph)
    .map((id) => {
      const kind = kinds.get(id) ?? "";
      return KIND_NAMES[kind] ?? kind;
    })
    .join(", ");
}

// --------------------------------------------------------------------------------------------------- the rows

export interface MapRow {
  /** The pipeline's identifier, which the order form carries and the page never shows. */
  id: string;
  name: string;
  status: string;
  version: string;
  stages: string;
  /** Whether the pipeline is deployed (the Studio's own rule: published, or flagged and still deployed). */
  deployed: boolean;
  /** What it runs after, in words; drawn only when an order is stored (`withOrder`). */
  runsAfter: string;
}

const byName = (a: Pipeline, b: Pipeline): number =>
  (a.label ?? "").localeCompare(b.label ?? "", "en-GB", { numeric: true, sensitivity: "base" }) ||
  String(a.recipe_id ?? "").localeCompare(String(b.recipe_id ?? ""), "en", { numeric: true });

/**
 * The table's rows for `datasetId`: each pipeline that loads that dataset and is not a previous version, sorted by name. A
 * pipeline placed in no dataset is left out, as is every other dataset's: the Conduit reads a case's pipelines through the
 * case's datasets, and this keeps to the one the page is open on. Nothing is counted: a row is a row.
 */
export function mapRows(registry: readonly Pipeline[], datasetId: string): MapRow[] {
  return registry
    .filter((p) => p.dataset_id === datasetId && p.status !== "superseded")
    .sort(byName)
    .map((p) => ({
      id: String(p.recipe_id ?? ""),
      deployed: isDeployed(p),
      runsAfter: "",
      name: p.label && p.label.trim() !== "" ? p.label : DATASET_MAP_WORDS.unnamed,
      status: p.status === undefined ? DATASET_MAP_WORDS.notRecorded : (STATUS_WORDS[p.status] ?? p.status),
      version: typeof p.version === "number" ? `v${p.version}` : DATASET_MAP_WORDS.notRecorded,
      stages: stageWords(p.pipeline) ?? DATASET_MAP_WORDS.notRecorded,
    }));
}

// ------------------------------------------------------------------------------------------------ the stored order

/** The stored order as the Conduit answered it: its number, who saved it and when, and the links the reader may see. */
export interface StoredOrder {
  version: number;
  savedBy: string | null;
  savedAt: string | null;
  /** Each pipeline that runs after another, with the pipelines it runs after (by identifier). */
  links: Map<string, string[]>;
}

/** The order read from the Conduit's answer, or `undefined` when the answer is not one (a failing service is never "none stored"). */
export function readOrder(body: unknown): StoredOrder | undefined {
  const said = body as { version?: unknown; saved_by?: unknown; saved_at?: unknown; entries?: unknown } | null | undefined;
  if (typeof said !== "object" || said === null) return undefined;
  if (typeof said.version !== "number" || !Number.isInteger(said.version) || said.version < 0 || !Array.isArray(said.entries)) return undefined;
  const links = new Map<string, string[]>();
  for (const entry of said.entries as unknown[]) {
    const e = entry as { pipeline_id?: unknown; runs_after?: unknown } | null;
    if (typeof e !== "object" || e === null || typeof e.pipeline_id !== "string" || !Array.isArray(e.runs_after)) return undefined;
    if (!e.runs_after.every((q) => typeof q === "string")) return undefined;
    links.set(e.pipeline_id, e.runs_after as string[]);
  }
  return {
    version: said.version,
    savedBy: typeof said.saved_by === "string" ? said.saved_by : null,
    savedAt: typeof said.saved_at === "string" ? said.saved_at : null,
    links,
  };
}

/** A pipeline as the order names it: its name, and "not deployed" in words when it is not. */
function named(row: MapRow): string {
  return row.deployed ? row.name : `${row.name} (${DATASET_MAP_WORDS.notDeployed})`;
}

/**
 * Whether the "Runs after" column is drawn: only when an order is stored and says something about a pipeline in the table. An
 * order saved with no link, or one whose links all name something this table does not hold, draws no column (never an empty one).
 */
export function drawsOrder(rows: readonly MapRow[], order: StoredOrder | undefined): boolean {
  if (order === undefined || order.version < 1) return false;
  const ids = new Set(rows.map((r) => r.id));
  return [...order.links].some(([pipeline, after]) => ids.has(pipeline) && after.some((q) => ids.has(q) && q !== pipeline));
}

/** The rows with what each runs after, in words, sorted by name; only the pipelines the table holds are named, and none is counted. */
export function withOrder(rows: readonly MapRow[], order: StoredOrder): MapRow[] {
  const byId = new Map(rows.map((r) => [r.id, r]));
  return rows.map((row) => {
    const after = (order.links.get(row.id) ?? [])
      .map((id) => byId.get(id))
      .filter((r): r is MapRow => r !== undefined && r.id !== row.id)
      .sort((a, b) => a.name.localeCompare(b.name, "en-GB", { numeric: true, sensitivity: "base" }) || a.id.localeCompare(b.id, "en"));
    return { ...row, runsAfter: after.length === 0 ? DATASET_MAP_WORDS.runsAfterNothing : after.map(named).join(", ") };
  });
}

/** The line that says which version of the order is shown, who saved it and when; empty when none is stored. */
export function orderLine(order: StoredOrder | undefined): string {
  if (order === undefined || order.version < 1) return "";
  return DATASET_MAP_WORDS.orderLine(order.version, order.savedBy, order.savedAt === null ? null : whenWords(order.savedAt));
}

// ------------------------------------------------------------------------------------------------ the form

/** One tick box of the form: pipeline `id` runs after `after`. Its value is what the form sends back: both identifiers, encoded. */
export interface Choice {
  id: string;
  label: string;
  value: string;
  checked: boolean;
}

export interface Fieldset {
  legend: string;
  choices: Choice[];
}

/** The separator of a tick box's value: `encodeURIComponent` never leaves one in an identifier. */
const SEP = "|";
export const linkValue = (pipeline: string, after: string): string => `${encodeURIComponent(pipeline)}${SEP}${encodeURIComponent(after)}`;

/** A tick box's value as the pair it names, or `undefined` for anything the page's own form would not send. */
export function parseLink(value: string): [string, string] | undefined {
  const parts = value.split(SEP);
  if (parts.length !== 2 || parts[0] === "" || parts[1] === "") return undefined;
  try {
    return [decodeURIComponent(parts[0] as string), decodeURIComponent(parts[1] as string)];
  } catch {
    return undefined;
  }
}

/**
 * The form's fieldsets: for each pipeline, a tick box for every other pipeline, ticked as the stored order says, or as the person
 * typed when `typed` is given (a refused save is drawn again with what was ticked).
 */
export function fieldsets(rows: readonly MapRow[], order: StoredOrder | undefined, typed: ReadonlySet<string> | undefined): Fieldset[] {
  return rows.map((row) => ({
    legend: DATASET_MAP_WORDS.legend(row.name),
    choices: rows
      .filter((other) => other.id !== row.id)
      .map((other) => {
        const value = linkValue(row.id, other.id);
        return {
          id: `link-${encodeURIComponent(row.id)}-${encodeURIComponent(other.id)}`,
          label: named(other),
          value,
          checked: typed !== undefined ? typed.has(value) : (order?.links.get(row.id) ?? []).includes(other.id),
        };
      }),
  }));
}
