/**
 * The boards page's words and the views it is drawn from (slice GG4a; ADR-143 decisions 3 to 5; ADR-152 decisions 5, 6 and 12; FUNCTIONS
 * row `drawing-boards`; scenario BD). Nothing here is a call or a right: a word, or a function from what the Conduit answered to what the
 * template draws.
 *
 * What the page says of a moment is the shared package's (`utcStampOf`, the case picker's way of writing one), imported and never written
 * again here. What it calls an item and a link is the React board's rule (`apps/workspace/src/boards/boardModel.ts`, `itemLabel` and
 * `linkLabel`), restated here because that file is the workspace's: `test/govuk/boards.test.ts` BD3 holds the two in step, and moving the
 * rule to the shared package is a later slice's (the slice's report). `apps/pages/scripts/build.mjs` bundles this file with the package, as
 * it does `casesWords.ts`.
 *
 * **The strict reader.** A body is read field by field against the routes' models: `Board` and `BoardOpened`
 * (`packages/schemas/boards.py`), `Node`, `Edge`, `Provenance`, `DrawnAssertion`, `Grading` and `Handling` (`packages/schemas/domain.py`),
 * and the cap's `LimitExceeded` (`services/api/working_set/models.py`). Every field the route sends (`REQUIRED`) must be there, of its type
 * and within the model's own limits (a time written as the Conduit writes one, a grade's parts not empty, a drawn item with a source); a
 * field a model leaves out when unset (`MAY_BE_ABSENT`) may be absent, and is read as strictly when it is there. A body missing one, or
 * with one of another shape, is not a view (`undefined`), said as "could not be read", never as a zero, an empty table or an empty board
 * (rule 2). So is a body that is not the one asked for (a board of another case, or another board), one that names an element twice, one
 * whose `drawn` list and whose elements' assertions disagree, and one with a link whose end is not among the items sent: the page never
 * looks an end up elsewhere. What is nested in a field the page leaves out (an element's audit, its resolution, a source reference, a
 * position) is read only as being of its kind.
 * **The field census.** `CENSUS` names, for each model, the fields the page draws, the fields it reads only to know the body is the one it
 * asked for (`checked`: a change makes the body one the page cannot draw from), and the fields it leaves out; Scenario BD's "Left out, by
 * field name" and "Checked, not drawn" sentences name the same, and `tests/glass_trees/test_govuk_boards_scenario.py` holds them to the
 * models' own fields.
 *
 * The views keep every board, item and link the Conduit sent, in the order it sent them: nothing here removes, cuts, sorts or counts
 * (decision 5; rule 3 stays with the Conduit and its adapters, which send only what the reader may see). The one split is of what was sent
 * into the items drawn and the items loaded, by the route's own `drawn` list: each item is in exactly one of the two tables. Plain words,
 * British English.
 */
import { utcStampOf } from "@ospreyflow/glass-shared";

import { caseBoardsHref, caseHref } from "./casesWords.js";

export const BOARDS_WORDS = {
  listTitle: "Drawing boards in this case",
  lede: "The drawing boards of this case you may see: your own, and those shared with the case. This page only shows them.",
  caption: "Drawing boards in this case",
  columns: ["Board", "Shared", "Drawn items", "Made"],
  // The React board's words for whether a board is shared (`apps/workspace/src/boards/BoardEditor.tsx`).
  shared: "Shared with the case",
  private: "Only you",
  drawnCount: (n: number): string => (n === 1 ? "1 drawn item" : `${n} drawn items`),
  // The React place's words (`apps/workspace/src/boards/BoardsPlace.tsx`).
  noBoards: "No boards in this case yet.",
  about: "About this board",
  sharedLabel: "Shared",
  made: "Made",
  drawnCaption: "Drawn items on this board",
  drawnColumns: ["Item", "Type", "Marking", "Grading", "Source note"],
  drawnNote: "Drawn, not loaded",
  noNote: "No note given",
  loadedCaption: "Loaded items on this board",
  loadedColumns: ["Item", "Type", "Marking"],
  // The React board's words for a loaded item (`apps/workspace/src/boards/BoardEditor.tsx`).
  loadedNote: "A dataset this case reads: a live reference, not editable here",
  linksCaption: "Links on this board",
  linkColumns: ["Link", "Type", "From", "To", "Drawn or loaded", "Marking", "Grading", "Source note"],
  drawn: "Drawn, not loaded",
  loaded: "Loaded",
  notGraded: "Not graded: loaded",
  loadedSource: "A dataset this case reads",
  // What is shown, never what is there: an item the reader may not see is in no table and no sentence (rule 3).
  emptyBoard: "No items are shown on this board.",
  nothingDrawn: "No drawn items are shown on this board.",
  nothingLoaded: "No loaded items are shown on this board.",
  noLinks: "No links are shown on this board.",
  withdrawn: (n: number): string => (n === 1 ? "1 item you placed has since been withdrawn." : `${n} items you placed have since been withdrawn.`),
  tooLargeTitle: "This board is too large to show",
  // The React canvas's figure for the cap (`apps/workspace/src/workingset/ViewOverCapDialog.tsx`, `figure`): the reader's own count.
  tooLarge: (wouldBe: number, kind: string, cap: number): string =>
    `Too many to show: ${wouldBe.toLocaleString("en-GB")} ${kind} against a limit of ${cap.toLocaleString("en-GB")}. Nothing of the board is shown.`,
  kinds: { nodes: "items", edges: "links", pairs: "pairs" },
  whatYouCanDo: "The ways on from here",
  optionWords: {
    save_as_view: "Save a smaller view: a view of this case that holds fewer items.",
    filter: "Apply a filter: narrow what you see to some types of item, or to a window of dates.",
    promote_to_batch: "Promote it to a batch job: the work runs on the server, and its result is saved as a view.",
  },
  noPageYet: "None of these has a page in this service yet, and none of them opens this board.",
  unreadableList: "The boards of this case could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  unreadableBoard: "This board could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  toCase: "Back to this case",
  toBoards: "Back to this case's boards",
  back: "Back to Home",
} as const;

/** Each model the page reads: the fields it draws, the fields it only checks, and the fields it leaves out (Scenario BD names the same). */
export const CENSUS = {
  Board: { drawn: ["id", "name", "created_at", "shared", "drawn"], checked: ["case_id"], left: ["created_by", "start"] },
  BoardOpened: { drawn: ["board", "nodes", "edges", "missing"], checked: ["drawn"], left: ["items", "layout", "node_types", "link_types", "markings", "ceiling", "grading_scheme", "grading_grades", "may_draw", "may_promote"] },
  Node: { drawn: ["type", "properties", "provenance", "handling"], checked: ["id"], left: ["resolution", "audit", "datasets"] },
  Edge: { drawn: ["type", "source", "target", "provenance", "handling"], checked: ["id"], left: ["properties", "interval", "occurrences", "weight", "weight_components", "basis", "audit", "datasets"] },
  Provenance: { drawn: ["drawn"], checked: [], left: ["state", "sources", "sources_withheld", "extracted_by", "extraction_confidence", "first_seen", "last_confirmed", "confirmed_by", "gazetteer"] },
  DrawnAssertion: { drawn: ["label", "grading", "source_note"], checked: ["provenance_class"], left: ["item_id", "asserted_by", "board_id", "case_id", "original_grading", "source_document", "icon"] },
  Grading: { drawn: ["scheme", "source", "intelligence", "handling"], checked: [], left: [] },
  Handling: { drawn: ["classification"], checked: [], left: ["handling_code", "action_code", "sanitisation_code", "originator", "owning_unit", "review_date", "legal_basis"] },
  LimitExceeded: { drawn: ["cap_kind", "cap", "would_be", "options"], checked: ["error"], left: [] },
} as const;

// Each named as `Model.field`: a bare name would take in every model's field of that name (`Board.drawn` is a count, always sent, where
// `Provenance.drawn` may be absent), which BD11's count of the required fields found.
/** A field of a model that is never on the wire (`exclude=True`): the reader does not ask for it. */
export const NOT_SENT: readonly string[] = ["Edge.weight_components"];
/** A field a model leaves out of what it sends when it is unset (its `model_serializer` pops it): the reader does not require it. */
export const MAY_BE_ABSENT: readonly string[] = ["Provenance.drawn", "Provenance.gazetteer"];

type Model = keyof typeof CENSUS;

/** Every field each model always sends: the strict reader asks for each one. */
export const REQUIRED = Object.fromEntries(
  Object.entries(CENSUS).map(([model, { drawn, checked, left }]) => [
    model,
    [...drawn, ...checked, ...left].filter((field) => !NOT_SENT.includes(`${model}.${field}`) && !MAY_BE_ABSENT.includes(`${model}.${field}`)),
  ]),
) as Record<Model, string[]>;

// The values each closed field may take: the models' own (`BoardStart`, `ProvenanceState`, `LimitOption`, and the `Literal`s of
// `Edge.basis`, `LimitExceeded.cap_kind` and `DrawnAssertion.provenance_class`), which `tests/glass_trees/test_govuk_boards_scenario.py`
// holds these lists to, so a value added to a model fails that test, not a reader's page.
export const STARTS = ["blank", "view", "selection"] as const;
export const STATES: readonly string[] = ["asserted", "inferred", "unresolved"];
export const OPTIONS = ["save_as_view", "filter", "promote_to_batch"] as const;
export const BASES: readonly string[] = ["direct", "probabilistic"];
export const CAP_KINDS = ["nodes", "edges", "pairs"] as const;
export const CLASSES: readonly string[] = ["analyst_drawn"];

type Option = (typeof OPTIONS)[number];
type Json = Record<string, unknown>;

const isObject = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";
const isFilled = (value: unknown): value is string => isText(value) && value.length > 0;
const isTextOrNull = (value: unknown): boolean => value === null || isText(value);
const isTexts = (value: unknown): value is string[] => Array.isArray(value) && (value as unknown[]).every(isText);
const isCount = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isNumberOrNull = (value: unknown): boolean => value === null || isNumber(value);
/** A moment as the Conduit writes one (ISO 8601 with a time), which `utcStampOf` can draw; a bare number or year is not one. */
const MOMENT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/;
const isTime = (value: unknown): value is string => isText(value) && MOMENT.test(value) && !Number.isNaN(new Date(value).getTime());
const isTimeOrNull = (value: unknown): boolean => value === null || isTime(value);
const isDateOrNull = (value: unknown): boolean => value === null || (isText(value) && /^\d{4}-\d{2}-\d{2}$/.test(value));
const isObjectOrNull = (value: unknown): boolean => value === null || isObject(value);
const isTextMap = (value: unknown): boolean => isObject(value) && Object.values(value).every(isText);
const isObjects = (value: unknown): boolean => Array.isArray(value) && (value as unknown[]).every(isObject);
const distinct = (ids: readonly string[]): boolean => new Set(ids).size === ids.length;

// Each field is checked for its type, and `undefined` is no required field's type, so a missing field is refused by the same check as a
// wrong one (GR1a found a separate presence check could not fail on its own). `test/govuk/boards.test.ts` BD11 removes each field of
// `REQUIRED` in turn, and gives each a wrong shape.

/** The address of a case's boards, and of one board: one page with the case and the board in its query (`pages.ts`: a plain path). */
export const boardsHref = caseBoardsHref;
export const boardHref = (caseId: string, boardId: string): string => `${caseBoardsHref(caseId)}&board=${encodeURIComponent(boardId)}`;

// ------------------------------------------------------------------------------------------------ the models, read strictly

interface Grade {
  scheme: string;
  source: string;
  intelligence: string;
  handling: string;
}

function gradingOf(body: unknown): Grade | undefined {
  if (!isObject(body)) return undefined;
  const { scheme, source, intelligence, handling } = body;
  if (!isFilled(scheme) || !isFilled(source) || !isFilled(intelligence) || !isFilled(handling)) return undefined;
  return { scheme, source, intelligence, handling };
}

interface Assertion {
  label: string;
  grading: Grade;
  source_note: string | null;
}

function assertionOf(body: unknown): Assertion | undefined {
  if (!isObject(body)) return undefined;
  const { provenance_class, item_id, asserted_by, board_id, case_id, label, grading, original_grading, source_note, source_document, icon } = body;
  if (!CLASSES.includes(provenance_class as string) || !isText(item_id) || !isText(asserted_by) || !isText(board_id) || !isText(case_id)) return undefined;
  const grade = gradingOf(grading);
  if (!isFilled(label) || grade === undefined || !(original_grading === null || gradingOf(original_grading) !== undefined)) return undefined;
  if (!isTextOrNull(source_note) || !isTextOrNull(source_document) || !isTextOrNull(icon)) return undefined;
  // A drawn item has a source note, a document of the case, or both; never neither (`DrawnAssertion._has_a_source`).
  const noted = isText(source_note) && source_note.trim() !== "";
  if (!noted && !isFilled(source_document)) return undefined;
  return { label, grading: grade, source_note: noted ? (source_note as string) : null };
}

/** A provenance, with its assertion when it carries one; `undefined` when it is not one. */
function provenanceOf(body: unknown): { drawn: Assertion | undefined } | undefined {
  if (!isObject(body)) return undefined;
  const { state, sources, sources_withheld, extracted_by, extraction_confidence, first_seen, last_confirmed, confirmed_by } = body;
  if (!STATES.includes(state as string) || !isObjects(sources) || typeof sources_withheld !== "boolean") return undefined;
  if (!isTextOrNull(extracted_by) || !isNumberOrNull(extraction_confidence) || !isTime(first_seen) || !isTimeOrNull(last_confirmed)) return undefined;
  if (!isTextOrNull(confirmed_by)) return undefined;
  // Left out of what is sent when unset (`Provenance._leave_out_undrawn`), and read as strictly when there.
  if ("gazetteer" in body && !isTextOrNull(body["gazetteer"])) return undefined;
  if (!("drawn" in body) || body["drawn"] === null) return { drawn: undefined };
  const drawn = assertionOf(body["drawn"]);
  return drawn === undefined ? undefined : { drawn };
}

/** A handling, said by its classification (the React board's marking); `undefined` when it is not one. */
function markingOf(body: unknown): string | undefined {
  if (!isObject(body)) return undefined;
  const { classification, handling_code, action_code, sanitisation_code, originator, owning_unit, review_date, legal_basis } = body;
  if (!isFilled(classification) || !isText(handling_code) || !isTextOrNull(action_code) || !isTextOrNull(sanitisation_code)) return undefined;
  if (!isText(originator) || !isText(owning_unit) || !isDateOrNull(review_date) || !isTextOrNull(legal_basis)) return undefined;
  return classification;
}

interface Element {
  id: string;
  type: string;
  marking: string;
  drawn: Assertion | undefined;
}

interface NodeRead extends Element {
  properties: Json;
}

function nodeOf(body: unknown): NodeRead | undefined {
  if (!isObject(body)) return undefined;
  const { id, type, properties, provenance, handling, resolution, audit, datasets } = body;
  if (!isFilled(id) || !isFilled(type) || !isObject(properties) || !isObject(resolution) || !isObject(audit) || !isTexts(datasets)) return undefined;
  const read = provenanceOf(provenance);
  const marking = markingOf(handling);
  if (read === undefined || marking === undefined) return undefined;
  return { id, type, properties, marking, drawn: read.drawn };
}

interface EdgeRead extends Element {
  source: string;
  target: string;
}

function edgeOf(body: unknown): EdgeRead | undefined {
  if (!isObject(body)) return undefined;
  const { id, type, source, target, properties, interval, occurrences, weight, basis, provenance, handling, audit, datasets } = body;
  if (!isFilled(id) || !isFilled(type) || !isText(source) || !isText(target) || !isObject(properties) || !isObjectOrNull(interval)) return undefined;
  if (!isCount(occurrences) || !isNumber(weight) || !(basis === null || BASES.includes(basis as string)) || !isObject(audit) || !isTexts(datasets)) return undefined;
  const read = provenanceOf(provenance);
  const marking = markingOf(handling);
  if (read === undefined || marking === undefined) return undefined;
  return { id, type, source, target, marking, drawn: read.drawn };
}

interface BoardRead {
  id: string;
  name: string;
  created_at: string;
  shared: boolean;
  drawn: number;
}

/** A board as listed, of the case asked for; `undefined` when it is not one. */
function boardOf(body: unknown, caseId: string): BoardRead | undefined {
  if (!isObject(body)) return undefined;
  const { id, case_id, name, created_by, created_at, shared, drawn, start } = body;
  if (!isFilled(id) || case_id !== caseId || !isFilled(name) || !isText(created_by) || !isTime(created_at)) return undefined;
  if (typeof shared !== "boolean" || !isCount(drawn) || !STARTS.some((known) => known === start)) return undefined;
  return { id, name, created_at, shared, drawn };
}

/** Each element of a list read by `read`, in the order sent; `undefined` when the body is not such a list. */
function each<T>(body: unknown, read: (row: unknown) => T | undefined): T[] | undefined {
  if (!Array.isArray(body)) return undefined;
  const out: T[] = [];
  for (const row of body as unknown[]) {
    const one = read(row);
    if (one === undefined) return undefined;
    out.push(one);
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ the views

const NAME_KEYS = ["name", "family_name", "value_normalised", "account_number", "title"] as const;

/** What the board calls an item: a drawn one by the analyst's own label, a loaded one by its name (the React board's rule). */
function itemLabel(node: NodeRead): string {
  if (node.drawn) return node.drawn.label;
  for (const key of NAME_KEYS) {
    const value = node.properties[key];
    if (typeof value === "string" && value.trim()) {
      const given = node.properties["given_names"];
      if (key === "family_name" && typeof given === "string" && given.trim()) return `${given} ${value}`;
      return value;
    }
  }
  return `Unnamed ${node.type}`;
}

/** What the board calls a link: a drawn one by its label, a loaded one by its type in words (the React board's rule). */
function linkLabel(edge: EdgeRead): string {
  if (edge.drawn) return edge.drawn.label;
  if (edge.type === "SAME_AS") return "same as";
  if (edge.type === "NOT_SAME_AS") return "not the same as";
  return edge.type.toLowerCase().replaceAll("_", " ");
}

/** A grade as the React board writes it: source, intelligence and handling, then the scheme. */
const gradeSaid = (g: Grade): string => `${g.source}${g.intelligence}${g.handling} (${g.scheme})`;
/** A source note as written. A source document is never said, not even by its kind: the route sends its identifier to every reader of
 * the board, whether or not they may read the document (a question in the slice's report, rule 3). */
const noteSaid = (d: Assertion): string => d.source_note ?? BOARDS_WORDS.noNote;

export interface BoardRow {
  href: string;
  name: string;
  shared: string;
  drawn: string;
  made: string;
}

export type ListView = { kind: "empty"; toCase: string } | { kind: "table"; rows: BoardRow[]; toCase: string };

/** A case's boards as the page draws them, or `undefined` when the body is not the route's for this case (said as a failure). */
export function listView(caseId: string, body: unknown): ListView | undefined {
  const boards = each(body, (row) => boardOf(row, caseId));
  if (boards === undefined || !distinct(boards.map((b) => b.id))) return undefined;
  const toCase = caseHref(caseId);
  if (boards.length === 0) return { kind: "empty", toCase };
  return {
    kind: "table",
    toCase,
    rows: boards.map((b) => ({
      href: boardHref(caseId, b.id),
      name: b.name,
      shared: b.shared ? BOARDS_WORDS.shared : BOARDS_WORDS.private,
      drawn: BOARDS_WORDS.drawnCount(b.drawn),
      made: utcStampOf(b.created_at),
    })),
  };
}

export interface DrawnRow {
  label: string;
  type: string;
  marking: string;
  grading: string;
  note: string;
}

export interface LoadedRow {
  label: string;
  type: string;
  marking: string;
}

export interface LinkRow {
  label: string;
  type: string;
  from: string;
  to: string;
  drawn: boolean;
  marking: string;
  grading: string;
  note: string;
}

export interface BoardView {
  kind: "board";
  name: string;
  shared: string;
  made: string;
  /** The route's `missing`, in words, when it sends more than zero (to the board's creator alone); otherwise `undefined`. */
  withdrawn: string | undefined;
  empty: boolean;
  drawn: DrawnRow[];
  loaded: LoadedRow[];
  links: LinkRow[];
}

/** One board as the page draws it, or `undefined` when the body is not the route's for this case and board, names an element twice, its
 * `drawn` list and its elements' assertions disagree, or a link's end is not among the items sent (said as a failure, never in part). */
export function boardView(caseId: string, boardId: string, body: unknown): BoardView | undefined {
  if (!isObject(body)) return undefined;
  const { board, nodes, edges, drawn, items, layout, missing, node_types, link_types, markings, ceiling, grading_scheme, grading_grades, may_draw, may_promote } = body;
  const read = boardOf(board, caseId);
  const nodesRead = each(nodes, nodeOf);
  const edgesRead = each(edges, edgeOf);
  if (read === undefined || read.id !== boardId || nodesRead === undefined || edgesRead === undefined || !isTexts(drawn) || !isCount(missing)) return undefined;
  if (!isTextMap(items) || !isObject(layout) || !isTexts(node_types) || !isTexts(link_types) || !isTexts(markings)) return undefined;
  if (!isTextOrNull(ceiling) || !isText(grading_scheme) || !isObjectOrNull(grading_grades) || typeof may_draw !== "boolean" || typeof may_promote !== "boolean") return undefined;
  const elementIds = [...nodesRead, ...edgesRead].map((element) => element.id);
  if (!distinct(elementIds) || !distinct(drawn)) return undefined;
  const drawnIds = new Set(drawn);
  // The route names as drawn exactly the elements that carry an assertion: a body where the two disagree is not one it sends.
  for (const element of [...nodesRead, ...edgesRead]) if (drawnIds.has(element.id) !== (element.drawn !== undefined)) return undefined;
  for (const id of drawn) if (!elementIds.includes(id)) return undefined;
  const byId = new Map(nodesRead.map((node) => [node.id, node]));
  const links: LinkRow[] = [];
  for (const edge of edgesRead) {
    const from = byId.get(edge.source);
    const to = byId.get(edge.target);
    if (from === undefined || to === undefined) return undefined;
    links.push({
      label: linkLabel(edge),
      type: edge.type,
      from: itemLabel(from),
      to: itemLabel(to),
      drawn: edge.drawn !== undefined,
      marking: edge.marking,
      grading: edge.drawn ? gradeSaid(edge.drawn.grading) : BOARDS_WORDS.notGraded,
      note: edge.drawn ? noteSaid(edge.drawn) : BOARDS_WORDS.loadedSource,
    });
  }
  return {
    kind: "board",
    name: read.name,
    shared: read.shared ? BOARDS_WORDS.shared : BOARDS_WORDS.private,
    made: utcStampOf(read.created_at),
    withdrawn: missing > 0 ? BOARDS_WORDS.withdrawn(missing) : undefined,
    empty: nodesRead.length === 0 && edgesRead.length === 0,
    drawn: nodesRead
      .filter((node) => drawnIds.has(node.id))
      .map((node) => {
        const d = node.drawn as Assertion;
        return { label: d.label, type: node.type, marking: node.marking, grading: gradeSaid(d.grading), note: noteSaid(d) };
      }),
    loaded: nodesRead.filter((node) => !drawnIds.has(node.id)).map((node) => ({ label: itemLabel(node), type: node.type, marking: node.marking })),
    links,
  };
}

export interface LimitView {
  kind: "too-large";
  says: string;
  options: string[];
}

/** The working-set cap's typed refusal (`LimitExceeded`, a 409) as the page says it, or `undefined` when the body is not one. */
export function limitView(body: unknown): LimitView | undefined {
  if (!isObject(body)) return undefined;
  const { error, cap_kind, cap, would_be, options } = body;
  if (error !== "limit_exceeded" || !CAP_KINDS.some((kind) => kind === cap_kind) || !isCount(cap) || !isCount(would_be)) return undefined;
  if (!Array.isArray(options) || options.length !== OPTIONS.length || !OPTIONS.every((option) => (options as unknown[]).includes(option))) return undefined;
  return {
    kind: "too-large",
    says: BOARDS_WORDS.tooLarge(would_be, BOARDS_WORDS.kinds[cap_kind as (typeof CAP_KINDS)[number]], cap),
    options: (options as Option[]).map((option) => BOARDS_WORDS.optionWords[option]),
  };
}
