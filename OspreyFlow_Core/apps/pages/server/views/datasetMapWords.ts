/**
 * The dataset map's words and the plain logic its table is made from (slice IS3; ADR-140 Amendment 22 items 1 and 8;
 * ADR-141 Amendment 2). The page is a read-only table of the pipelines that load one dataset: pipeline, status, version and
 * stages. Nothing here is a page or a call: a word, or a function from what the Conduit answered to the table's rows, so each
 * is a test's to read.
 *
 * What the table never says: a column for the order pipelines run in, a hint about it, or a line between two pipelines. That
 * column is IS6's, and it is drawn only once the order is stored (the owner's ruling of 21 November 2026); a page that
 * invented one now would show a person something nothing backs. `tests/glass_trees/test_dataset_map_scenario.py` fails on
 * those words in this file and in the template.
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
import { refusalWords } from "./studioWords.js";
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
  sorted: "Sorted by pipeline name.",
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
  name: string;
  status: string;
  version: string;
  stages: string;
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
      name: p.label && p.label.trim() !== "" ? p.label : DATASET_MAP_WORDS.unnamed,
      status: p.status === undefined ? DATASET_MAP_WORDS.notRecorded : (STATUS_WORDS[p.status] ?? p.status),
      version: typeof p.version === "number" ? `v${p.version}` : DATASET_MAP_WORDS.notRecorded,
      stages: stageWords(p.pipeline) ?? DATASET_MAP_WORDS.notRecorded,
    }));
}
