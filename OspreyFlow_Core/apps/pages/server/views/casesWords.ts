/**
 * The cases page's words and the views it is drawn from (slices GR1a and GR1e; ADR-152 decisions 5, 6 and 12; FUNCTIONS row
 * `cases-and-views`; scenario CS). Nothing here is a call or a right: a word, or a function from what the Conduit answered to what the template draws.
 *
 * What the page says of a level, a domain pack, an untitled case and a moment is the shared package's (`packages/glass-shared`): the
 * Help page's level names, the Studio's pack labels, the case picker's untitled name and its way of writing a moment, imported and never
 * written again here. `apps/pages/scripts/build.mjs` bundles this file with the package, as it does `helpWords.ts`.
 *
 * **The strict reader.** A body is read field by field against the route's model: `InvestigationListing` (`services/api/app.py`),
 * `Investigation` (`services/api/investigations.py`), `CaseBrief`, `BriefRequirement` and `BriefAttachment`
 * (`services/api/case_brief.py`) and `HistoryStepSummary` (`services/api/history.py`, GR1e). Every field the route sends (`REQUIRED`) must be there, of its type; a body missing one, or with one of
 * another shape, is not a view (`undefined`), said as "could not be read", never as a zero, an empty list or an empty brief (rule 2).
 * **The field census.** `CENSUS` names, for each model, the fields the page draws and the fields it leaves out; Scenario CS's "Left out,
 * by field name" sentence names the same, and `tests/glass_trees/test_govuk_cases_scenario.py` holds both to the models' own fields.
 *
 * The views keep every case, every requirement and every step the Conduit sent, in the order it sent them: nothing here removes, cuts, sorts or
 * counts (decision 5; rule 3 stays with the Conduit and its adapters, and the brief's route already leaves out an attachment the reader
 * may not read). Plain words, British English.
 */
import { LEVEL_WORDS, caseLabel, domainLabels, utcStampOf } from "@ospreyflow/glass-shared";
import type { DomainPack } from "@ospreyflow/glass-shared";

export const CASES_WORDS = {
  listTitle: "Your cases",
  lede: "The cases you hold a level on. This page only shows them.",
  caption: "Your cases",
  columns: ["Case", "Your level", "Domains", "Datasets", "Made"],
  closed: "You closed this case's tab",
  noCases: "You have no cases to show.",
  // An empty list is said as none shown, never as "none": the route sends no dataset to a reader holding no right (ADR-099
  // Amendment 11, `services/api/datasets.py`), so the page cannot tell a case that reads none from one whose datasets are withheld.
  noDatasets: "None shown",
  about: "About this case",
  level: "Your level",
  domains: "Domains",
  datasets: "Datasets",
  made: "Made",
  brief: "Brief",
  priority: "Priority information requirement",
  noPriority: "No priority information requirement is set.",
  requirements: "Information requirements",
  noRequirements: "No information requirements yet.",
  noBrief: "This case has no brief yet.",
  open: "Open",
  answered: "Answered",
  answeredOn: (when: string): string => `Answered on ${when}`,
  attached: "Attached to it",
  contentsTitle: "Contents",
  // The case page's parts, in order: each an address on the page (its heading's id) and the words of its link.
  contents: [
    { href: "#about", text: "About this case" },
    { href: "#brief", text: "Brief" },
    { href: "#history", text: "History" },
  ],
  history: "History",
  historyLede: "This page only shows the steps. It restores none.",
  historyCaption: "Changes to this case, in the order the case records them",
  historyColumns: ["Step", "When", "Restore"],
  canRestore: "Can be restored",
  cannotRestore: "Cannot be restored",
  noHistory: "Nothing has changed in this case yet.",
  kinds: { trend: "A saved trend", pattern: "A saved pattern", assessment: "An assessment", view: "A canvas view" },
  unreadableList: "Your cases could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  unreadableCase: "This case could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  toCases: "Back to your cases",
  back: "Back to Home",
} as const;

/** Each model the page reads: the fields it draws and the fields it leaves out (Scenario CS names the same). */
export const CENSUS = {
  InvestigationListing: { drawn: ["id", "name", "level", "created_at", "domains", "tab_hidden", "datasets"], left: ["created_by", "dataset_ids"] },
  Investigation: { drawn: ["name", "created_at", "domains"], left: ["id", "created_by", "owning_unit", "domains_chosen"] },
  CaseBrief: { drawn: ["priority", "requirements"], left: [] },
  BriefRequirement: { drawn: ["text", "status", "answered_at", "attachments"], left: ["id"] },
  BriefAttachment: { drawn: ["kind"], left: ["id", "title"] },
  HistoryStepSummary: { drawn: ["label", "created_at", "restorable"], left: ["id"] },
} as const;

/** A field of a model that is never on the wire (`exclude=True`): the reader does not ask for it. */
export const NOT_SENT: readonly string[] = ["domains_chosen"];

type Model = keyof typeof CENSUS;

/** Every field each model sends: the strict reader asks for each one. */
export const REQUIRED = Object.fromEntries(
  Object.entries(CENSUS).map(([model, { drawn, left }]) => [model, [...drawn, ...left].filter((field) => !NOT_SENT.includes(field))]),
) as Record<Model, string[]>;

// The values each closed field may take: the models' own (`AccessLevel`, `DomainPack`, `RequirementStatus`, `AttachmentKind`), which
// `tests/glass_trees/test_govuk_cases_scenario.py` holds these lists to, so a value added to a model fails that test, not a reader's page.
export const LEVELS = ["viewer", "editor", "author"] as const;
export const PACKS: readonly string[] = ["fibo", "niem", "stix"];
export const STATUSES = ["open", "answered"] as const;
export const KINDS = ["trend", "pattern", "assessment", "view"] as const;
// The labels `GET /history` can send: `history_labels.py`'s fixed labels and `Changed`, which the route sends for any stored label that is
// not one of them. The page draws a label as sent and never in words of its own; a label outside this list is a body it does not draw
// from (could not be read). The scenario test holds this list to that file.
export const HISTORY_LABELS: readonly string[] = ["Seeded", "Expanded", "Showed links among the view", "Removed", "Ran a starter question", "Showed two who share contacts", "Opened from an alert", "Showed an ownership structure", "Opened an alert", "Edited the brief", "Changed"];

type Level = (typeof LEVELS)[number];
type Kind = (typeof KINDS)[number];

export interface CaseRow {
  href: string;
  name: string;
  closed: boolean;
  level: string;
  domains: string;
  datasets: string[];
  made: string;
}

export type ListView = { kind: "empty" } | { kind: "table"; rows: CaseRow[] };

export interface RequirementRow {
  text: string;
  status: string;
  answered: string | undefined;
  attachments: string[];
}

export type BriefView = { kind: "none" } | { kind: "brief"; priority: string | undefined; requirements: RequirementRow[] };

export interface StepRow {
  label: string;
  when: string;
  restore: string;
}

export type HistoryView = { kind: "none" } | { kind: "steps"; rows: StepRow[] };

export interface CaseView {
  kind: "case";
  name: string;
  level: string;
  domains: string;
  datasets: string[];
  made: string;
  brief: BriefView;
  history: HistoryView;
}

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";
const isTexts = (value: unknown): value is string[] => Array.isArray(value) && (value as unknown[]).every(isText);
const isPacks = (value: unknown): value is DomainPack[] => isTexts(value) && value.every((pack) => PACKS.includes(pack));
const isLevel = (value: unknown): value is Level => LEVELS.some((level) => level === value);
const isLabel = (value: unknown): value is string => HISTORY_LABELS.some((label) => label === value);
/** A moment the page can write: a time `utcStampOf` would draw as given is a body the page does not draw from. */
const isTime = (value: unknown): value is string => isText(value) && !Number.isNaN(new Date(value).getTime());

// No separate presence check: each field is checked for its type below, and `undefined` is no field's type (`answered_at` is a time or
// `null`), so a missing field is refused by the same check as a wrong one. A presence check beside it was planted out and nothing went
// red: it could not fail on its own, so it is not here (rule 15). `test/govuk/cases.test.ts` CS10 removes each field of `REQUIRED` in turn.

/** The address of a case's page: one page with the case in its query (a page's path is a plain path: `pages.ts`). */
export const caseHref = (id: string): string => `/cases?case=${encodeURIComponent(id)}`;

/** One row of `GET /v1/investigations`, read strictly; `undefined` when it is not one. */
function listingOf(row: unknown):
  | { id: string; name: string; level: Level; created_at: string; domains: DomainPack[]; tab_hidden: boolean; datasets: string[] }
  | undefined {
  if (!isObject(row)) return undefined;
  const { id, name, level, created_at, created_by, domains, tab_hidden, datasets, dataset_ids } = row;
  if (!isText(id) || !isText(name) || !isLevel(level) || !isTime(created_at) || !isText(created_by)) return undefined;
  if (!isPacks(domains) || typeof tab_hidden !== "boolean" || !isTexts(datasets) || !isTexts(dataset_ids)) return undefined;
  return { id, name, level, created_at, domains, tab_hidden, datasets };
}

/** `GET /v1/investigations` as rows, every one in the order sent; `undefined` when it is not a list of listings. */
function listingsOf(body: unknown): NonNullable<ReturnType<typeof listingOf>>[] | undefined {
  if (!Array.isArray(body)) return undefined;
  const rows: NonNullable<ReturnType<typeof listingOf>>[] = [];
  for (const row of body as unknown[]) {
    const read = listingOf(row);
    if (read === undefined) return undefined;
    rows.push(read);
  }
  return rows;
}

/** The list page's view, or `undefined` when the body is not the route's (said as a failure). */
export function listView(body: unknown): ListView | undefined {
  const listings = listingsOf(body);
  if (listings === undefined) return undefined;
  if (listings.length === 0) return { kind: "empty" };
  return {
    kind: "table",
    rows: listings.map((row) => ({
      href: caseHref(row.id),
      name: caseLabel(row),
      closed: row.tab_hidden,
      level: LEVEL_WORDS[row.level].name,
      domains: domainLabels(row.domains),
      datasets: row.datasets,
      made: utcStampOf(row.created_at),
    })),
  };
}

function attachmentOf(body: unknown): Kind | undefined {
  if (!isObject(body)) return undefined;
  const { kind, id, title } = body;
  if (!KINDS.some((known) => known === kind) || !isText(id) || !isText(title)) return undefined;
  return kind as Kind;
}

function requirementOf(body: unknown): RequirementRow | undefined {
  if (!isObject(body)) return undefined;
  const { id, text, status, answered_at, attachments } = body;
  if (!isText(id) || !isText(text) || !STATUSES.some((known) => known === status)) return undefined;
  if (!(answered_at === null || isTime(answered_at)) || !Array.isArray(attachments)) return undefined;
  const kinds: string[] = [];
  for (const attachment of attachments as unknown[]) {
    const kind = attachmentOf(attachment);
    if (kind === undefined) return undefined;
    kinds.push(CASES_WORDS.kinds[kind]);
  }
  return {
    text,
    status: status === "answered" ? CASES_WORDS.answered : CASES_WORDS.open,
    answered: answered_at === null ? undefined : CASES_WORDS.answeredOn(utcStampOf(answered_at)),
    attachments: kinds,
  };
}

function briefOf(body: unknown): BriefView | undefined {
  if (!isObject(body)) return undefined;
  const { priority, requirements } = body;
  if (!isText(priority) || !Array.isArray(requirements)) return undefined;
  const rows: RequirementRow[] = [];
  for (const requirement of requirements as unknown[]) {
    const read = requirementOf(requirement);
    if (read === undefined) return undefined;
    rows.push(read);
  }
  if (priority.trim() === "" && rows.length === 0) return { kind: "none" };
  return { kind: "brief", priority: priority.trim() === "" ? undefined : priority, requirements: rows };
}

/** One step of `GET /history` (`HistoryStepSummary`), read strictly. Whether it can be restored is the route's `restorable`, never the
 * page's guess from the label; a step without it is not read as the model's default. */
function stepOf(body: unknown): StepRow | undefined {
  if (!isObject(body)) return undefined;
  const { id, label, created_at, restorable } = body;
  if (!isText(id) || !isLabel(label) || !isTime(created_at) || typeof restorable !== "boolean") return undefined;
  return { label, when: utcStampOf(created_at), restore: restorable ? CASES_WORDS.canRestore : CASES_WORDS.cannotRestore };
}

/** `GET /history` as rows, every step in the order sent (the route's: `seq`, then the time); `undefined` when it is not a list of steps. */
function historyOf(body: unknown): HistoryView | undefined {
  if (!Array.isArray(body)) return undefined;
  const rows: StepRow[] = [];
  for (const step of body as unknown[]) {
    const read = stepOf(step);
    if (read === undefined) return undefined;
    rows.push(read);
  }
  return rows.length === 0 ? { kind: "none" } : { kind: "steps", rows };
}

/**
 * One case's page (`caseId`, the address's), from its own read (`Investigation`), its brief (`CaseBrief`), its history
 * (`list[HistoryStepSummary]`) and the list (for the reader's level on it and the datasets it reads, which the case's own route does not
 * send); `undefined` when any is not the route's, or the list does not hold the case (it is never drawn without its level).
 */
export function caseView(caseId: string, investigation: unknown, brief: unknown, history: unknown, list: unknown): CaseView | undefined {
  if (!isObject(investigation)) return undefined;
  const { id, name, created_at, created_by, owning_unit, domains } = investigation;
  if (!isText(id) || !isText(name) || !isTime(created_at) || !isText(created_by) || !isText(owning_unit) || !isPacks(domains)) return undefined;
  const listings = listingsOf(list);
  const briefView = briefOf(brief);
  const historyView = historyOf(history);
  if (listings === undefined || briefView === undefined || historyView === undefined) return undefined;
  const listed = listings.find((row) => row.id === caseId);
  if (listed === undefined) return undefined;
  return {
    kind: "case",
    name: caseLabel({ name, created_at }),
    level: LEVEL_WORDS[listed.level].name,
    domains: domainLabels(domains),
    datasets: listed.datasets,
    made: utcStampOf(created_at),
    brief: briefView,
    history: historyView,
  };
}
