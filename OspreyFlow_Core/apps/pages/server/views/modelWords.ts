/**
 * The Model step's words and the plain logic its tables are made from (slice IS2a; ADR-140 Amendment 22 items 1, 3 and 4;
 * ADR-152 decisions 6, 7 and 12). The page shows one dataset's domain model: the draft's types and the live version's, each in
 * a table, with who holds the draft and the forms to open, save and discard it. Nothing here is a page or a call: a word, or a
 * function from what the Conduit answered to the table's rows, so each is a test's to read.
 *
 * What the page never says: the old word for a pipeline (the screens say Pipeline, as `ingest/studio/vocabulary.ts` has it) and the
 * old word for the domain model (ADR-140 Amendment 9 decision 1). `tests/glass_trees/test_model_step_scenario.py` fails on
 * either in this file and in the template.
 *
 * A type is drawn from the draft's own records: an entity type's class, identifiers and matching rule, and the property records
 * that name it (`on_type`), each with whether it is indexed. A type the dataset's model adds is all this table lists: the POLE
 * core and the packs are named in a sentence (`modelInWords`), since they are the ontology's and not this dataset's.
 *
 * What the Conduit says about a refusal is shown only when it is the store's own words (a 409 `model_refused`): any other
 * answer is the page's own sentence, so nothing of a Conduit's body or a right's identifier is ever drawn.
 */
import { PACKS, modelInWords, refusalWords, workspaceStudioHref } from "./studioWords.js";

// ------------------------------------------------------------------------------------------------ what the Conduit sends

export interface MatchingRule {
  match_on: string;
  on_match: string;
}

/** An extension as `ModelExtension` serialises it: every field of it, the ones that do not apply null or empty. */
export interface Extension {
  name: string;
  kind: string;
  on_type?: string | null;
  added_in?: number;
  retired_in?: number | null;
  pole_class?: string | null;
  identifiers?: string[];
  matching?: MatchingRule | null;
  value_type?: string | null;
  indexed?: boolean;
}

/** One version of the domain model, as `TargetModel` serialises it. */
export interface ModelVersion {
  dataset_id?: string;
  version: number;
  state: string;
  packs: Record<string, number>;
  extensions: Extension[];
  reference_lists: string[];
  created_at: string;
  created_by: string;
  made_live_at?: string | null;
  made_live_by?: string | null;
  /** The draft's revision: changes on every save and is never one a draft had before. A save and a discard carry it with the version. */
  revision?: string | null;
}

export interface ModelRead {
  live: ModelVersion | null;
  draft: ModelVersion | null;
}

const KINDS = ["entity_type", "link_type", "property"];
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function validExtension(value: unknown): value is Extension {
  return (
    isObject(value) &&
    typeof value["name"] === "string" &&
    typeof value["kind"] === "string" &&
    KINDS.includes(value["kind"]) &&
    (value["identifiers"] === undefined || (Array.isArray(value["identifiers"]) && value["identifiers"].every((i) => typeof i === "string"))) &&
    (value["matching"] === undefined || value["matching"] === null || (isObject(value["matching"]) && typeof value["matching"]["match_on"] === "string"))
  );
}

function validVersion(value: unknown): value is ModelVersion {
  return (
    isObject(value) &&
    typeof value["version"] === "number" &&
    Number.isInteger(value["version"]) &&
    value["version"] >= 1 &&
    isObject(value["packs"]) &&
    Object.values(value["packs"]).every((pinned) => typeof pinned === "number") &&
    Array.isArray(value["extensions"]) &&
    value["extensions"].every(validExtension) &&
    Array.isArray(value["reference_lists"]) &&
    typeof value["created_at"] === "string" &&
    typeof value["created_by"] === "string"
  );
}

/** What `GET /v1/datasets/{id}/model` answered, or `undefined` when it is not a model at all: never an empty model made of nothing. */
export function readModel(json: unknown): ModelRead | undefined {
  if (!isObject(json)) return undefined;
  const live = json["live"] ?? null;
  const draft = json["draft"] ?? null;
  if ((live !== null && !validVersion(live)) || (draft !== null && !validVersion(draft))) return undefined;
  // A draft the page cannot name the revision of is one it cannot save or discard safely: not drawn as a model.
  if (draft !== null && revisionOf(draft.revision ?? undefined) === undefined) return undefined;
  return { live, draft };
}

// ------------------------------------------------------------------------------------------------------------- the words

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** A moment as the store words it: `20 November 2026 at 09:30 UTC`. Text a person cannot read as a date is said as it came. */
export function whenWords(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${two(at.getUTCDate())} ${MONTHS[at.getUTCMonth()] as string} ${at.getUTCFullYear()} at ${two(at.getUTCHours())}:${two(at.getUTCMinutes())} UTC`;
}

/** The five classes the ontology has (`PoleClass`), in the Studio's words. */
const CLASS_WORDS: Record<string, string> = {
  person: "Person",
  object: "Object",
  location: "Location",
  event: "Event",
  organisation: "Organisation",
};

export const MODEL_WORDS = {
  title: "Ingest Studio · Model",
  heading: "Domain model",
  intro: "Every pipeline that loads this dataset maps into its domain model, which is the POLE core with the packs and types shown here.",
  draftHeading: "Draft",
  liveHeading: "Live",
  draftCaption: (datasetName: string) => `Types in the draft of ${datasetName}`,
  liveCaption: (datasetName: string) => `Types in the live model of ${datasetName}`,
  columns: ["Type", "Class", "Identifiers", "Matching rule", "Properties"] as const,
  builtOn: (packs: Record<string, number>) => `Built on: ${modelInWords(Object.keys(packs))}`,
  held: (version: number, by: string, opened: string) => `Draft version ${version}, opened by ${by} on ${opened}.`,
  liveVersion: (version: number, by: string | null, made: string | null) =>
    by !== null && made !== null ? `Version ${version}, made live by ${by} on ${made}.` : `Version ${version}.`,
  notYours: (by: string) => `Only ${by} can save into or discard this draft.`,
  /** The proposed link types are decided in the workspace's Model tab until they are a page of this service: the link goes there and asks it to open on Model. */
  proposals: (n: number) => `${n === 1 ? "1 proposed link type waits" : `${n} proposed link types wait`} for you to decide. Open the Model tab in the workspace to decide them.`,
  proposalsLink: "Decide the proposed link types",
  proposalsHref: (caseId: string) => workspaceStudioHref(caseId),
  noDraft: "There is no draft of the domain model. Open one to change it; nothing that runs changes until a version is made live.",
  noLive: "This dataset has no live domain model yet: it uses the POLE core until one is made live.",
  noTypes: "This version adds no types of its own: it is the POLE core with its packs.",
  open: "Open a draft",
  save: "Save draft",
  discard: "Discard draft",
  packsLegend: "Starter packs",
  packLabel: (label: string) => `Version of the ${label} pack (leave blank to leave it out)`,
  none: "None",
  notRecorded: "Not recorded",
  noRule: "No matching rule",
  retired: (version: number) => `retired in version ${version}`,
  indexed: "indexed",
  notIndexed: "not indexed",
  unreadable: "The domain model of this dataset could not be read just now. Try again in a few minutes.",
  /**
   * One sentence for every reason the model is not drawn for a person: they lack the right to edit it, the Conduit no longer
   * opens the dataset, no case of theirs loads into it, or there is no such dataset. The Conduit answers a thing a person may
   * not see exactly as one that does not exist, and so does this page (rule 3: no oracle).
   */
  refused: refusalWords(403, undefined, "The domain model"),
  saveFailed: "The draft could not be saved just now. Nothing was changed, and what you typed is still in the form. Try again in a few minutes.",
  discardFailed: "The draft could not be discarded just now. Nothing was changed. Try again in a few minutes.",
  openFailed: "The draft could not be opened just now. Nothing was changed. Try again in a few minutes.",
  notUnderstood: "That request was not understood.",
  saved: (version: number) => `Draft saved as version ${version}. Nothing that runs has changed.`,
  discarded: "Draft discarded. Nothing that runs has changed.",
  opened: (version: number) => `Draft opened as version ${version}.`,
  badPin: (label: string) => `The version of the ${label} pack must be a whole number of 1 or more, or blank.`,
  /** The person's copy was read at a version the draft no longer is: said first, then the store's own words. */
  outOfDate: (now: number, did: "saved" | "discarded") =>
    did === "saved"
      ? `Your copy of the draft was out of date: it is now version ${now}. Nothing was saved. What you typed is kept in the form below; check it against the draft shown, then save again.`
      : `Your copy of the draft was out of date: it is now version ${now}. Nothing was discarded. Check the draft shown, then discard it again if you still mean to.`,
  /** The version is the same but the draft is not the one read: it was saved again, or discarded and opened again, since. */
  changedSince: (version: number, did: "saved" | "discarded") =>
    did === "saved"
      ? `Your copy of the draft was out of date: it was saved again, or discarded and opened again, after you read it (it is still version ${version}). Nothing was saved. What you typed is kept in the form below; check it against the draft shown, then save again.`
      : `Your copy of the draft was out of date: it was saved again, or discarded and opened again, after you read it (it is still version ${version}). Nothing was discarded. Check the draft shown, then discard it again if you still mean to.`,
  draftGone: (did: "saved" | "discarded") =>
    did === "saved"
      ? "Your copy of the draft was out of date: the draft you were looking at is no longer there. Nothing was saved. What you typed is kept below; open a draft and enter it again."
      : "Your copy of the draft was out of date: the draft you were looking at is no longer there. Nothing was discarded.",
  /** What was typed when there is no form to hold it (no draft now, or one that is another person's): kept on the page, not lost. */
  keptHeading: "What you typed",
  keptIntro: "This is what you typed, kept here so it is not lost. Nothing of it was saved.",
  keptLine: (label: string, value: string) => `Version of the ${label} pack: ${value.trim() === "" ? "left out" : value}`,
  /** A Conduit's refusal that is not the store's own words: the page's sentence, with no body of the Conduit's in it. */
  refusedWith: (what: string, status: number) => `${what} was refused (${status}).`,
} as const;

// -------------------------------------------------------------------------------------------------------------- the rows

export interface TypeRow {
  name: string;
  klass: string;
  identifiers: string;
  rule: string;
  properties: string;
}

const byName = (a: string, b: string): number => a.localeCompare(b, "en-GB", { numeric: true, sensitivity: "base" }) || (a < b ? -1 : a > b ? 1 : 0);

function ruleWords(matching: MatchingRule | null | undefined): string {
  if (!matching) return MODEL_WORDS.noRule;
  return matching.on_match === "create"
    ? `Matches on ${matching.match_on}: a new record is made each time`
    : `Matches on ${matching.match_on}: an existing record is used`;
}

/**
 * The table's rows for a version: each entity type the dataset's model adds, sorted by name, with its class, identifiers,
 * matching rule and the properties that name it, each with whether it is indexed. A property is a property of its type and
 * never a row of its own; one that names a type this version does not add (a property on a core type) is not in this table.
 * Nothing is counted: a row is a row.
 */
export function typeRows(extensions: readonly Extension[]): TypeRow[] {
  const properties = new Map<string, Extension[]>();
  for (const extension of extensions) {
    if (extension.kind === "property" && typeof extension.on_type === "string") {
      properties.set(extension.on_type, [...(properties.get(extension.on_type) ?? []), extension]);
    }
  }
  return extensions
    .filter((extension) => extension.kind === "entity_type")
    .sort((a, b) => byName(a.name, b.name))
    .map((type) => {
      const retired = typeof type.retired_in === "number" ? ` (${MODEL_WORDS.retired(type.retired_in)})` : "";
      const held = (properties.get(type.name) ?? [])
        .sort((a, b) => byName(a.name, b.name))
        .map((p) => {
          const flag = p.indexed === true ? MODEL_WORDS.indexed : MODEL_WORDS.notIndexed;
          const gone = typeof p.retired_in === "number" ? `, ${MODEL_WORDS.retired(p.retired_in)}` : "";
          return `${p.name} (${flag}${gone})`;
        });
      const identifiers = type.identifiers ?? [];
      return {
        name: `${type.name}${retired}`,
        klass: type.pole_class ? (CLASS_WORDS[type.pole_class] ?? type.pole_class) : MODEL_WORDS.notRecorded,
        identifiers: identifiers.length > 0 ? identifiers.join(", ") : MODEL_WORDS.none,
        rule: ruleWords(type.matching),
        properties: held.length > 0 ? held.join("; ") : MODEL_WORDS.none,
      };
    });
}

/** The pack a form field is named for, the label the Studio gives it and the field's name and id. */
export const PACK_FIELDS = PACKS.map((pack) => ({ name: pack.name, label: pack.label, field: `pack_${pack.name}`, id: `pack-${pack.name}` }));

/** What a pin field holds when the draft is first drawn: the version a pack is pinned at, or nothing for a pack left out. */
export function pinsOf(packs: Record<string, number>): Record<string, string> {
  return Object.fromEntries(PACK_FIELDS.map((pack) => [pack.field, packs[pack.name] === undefined ? "" : String(packs[pack.name])]));
}

/**
 * The packs a save sends, from what was typed: a blank is a pack left out, a whole number of 1 or more is a pin. A value that is
 * neither is named in words and nothing is sent.
 */
export function packsFrom(typed: Record<string, string>): { packs: Record<string, number> } | { problem: string } {
  const packs: Record<string, number> = {};
  for (const pack of PACK_FIELDS) {
    const text = (typed[pack.field] ?? "").trim();
    if (text === "") continue;
    if (!/^[0-9]{1,6}$/.test(text) || Number(text) < 1) return { problem: MODEL_WORDS.badPin(pack.label) };
    packs[pack.name] = Number(text);
  }
  return { packs };
}

/** A revision a form carried: the token the Conduit made (letters, digits, hyphen and underscore, 1 to 64), else undefined. */
export function revisionOf(text: string | undefined): string | undefined {
  return text !== undefined && /^[A-Za-z0-9_-]{1,64}$/.test(text) ? text : undefined;
}

/** A version number a form carried: a whole number of 1 or more, else undefined (a request the page did not make). */
export function versionOf(text: string | undefined): number | undefined {
  return text !== undefined && /^[0-9]{1,9}$/.test(text) && Number(text) >= 1 ? Number(text) : undefined;
}

/**
 * The words to show for a Conduit's refusal of a write: the store's own (a 409 whose `error` is `model_refused`, which names who
 * holds a draft and none of what is in it) when that is what it is, else a sentence of the page's with no body of the Conduit's.
 */
export function storeWords(status: number, body: unknown, what: string): string {
  const said = body as { error?: unknown; detail?: unknown } | undefined;
  if (status === 409 && said?.error === "model_refused" && typeof said.detail === "string" && said.detail.trim() !== "" && said.detail.length <= 1000) {
    return said.detail;
  }
  return MODEL_WORDS.refusedWith(what, status);
}
