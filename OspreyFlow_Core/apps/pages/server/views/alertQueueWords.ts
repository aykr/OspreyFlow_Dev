/**
 * The alert queue page's words and the readers of what the Conduit sends it (slice RM1a; ADR-152 decisions 6 and 12; FUNCTIONS row
 * `alerts-rules-watches`; scenario AQ). Plain words, British English. The kinds and the states are the React queue's
 * (`apps/workspace/src/alerts/AlertQueue.tsx`), so a reader meets the same word in either tree.
 *
 * What the page draws of an alert is five things and no more: its own words (`summary`), its kind, its state (with who holds it when the
 * Conduit names them, and whether it is suppressed), when it was raised, and the case. The readers below take those and leave the rest of
 * the row where it is: an entity, a citation, an id or what the alert rests on is never read, so it cannot be drawn (rule 7). Two fields of the
 * alert are read for the kind's words and for nothing else, as the React queue's `alertTitle` reads them: the typology of a typology alert
 * (named by `typologyWords`) and the rule of an analyst's (a rule beginning `analyst:dataset:` is a "Dataset alert", which reaches every
 * case that reads the dataset); the typology's key and the rule's id are never drawn.
 *
 * **The readers are strict, and read nothing that is not there.** A queue is the list the Conduit's route sends; a row that lacks a field
 * the route always sends, or holds one the route never sends (a state or a kind it does not have, a time that is not one), makes the whole
 * queue "could not be read", never a row with a guess in it and never an empty queue (rule 2). The page filters, counts and orders nothing:
 * every row sent is a row drawn, in the order sent.
 */

export const ALERT_QUEUE_WORDS = {
  title: "Alert queue",
  queueLede: "The alerts the service sends you for this case. This page only shows them.",
  casesLede: "Choose a case to see its alert queue.",
  columns: ["Alert", "Kind", "State", "When", "Case"],
  captionFor: "Open, claimed and closing alerts in",
  thisCaseLower: "this case",
  thisCase: "This case",
  empty: "There are no alerts for you to see in this case.",
  unreadable: "The alert queue could not be read. Nothing has changed. Try again in a few minutes.",
  noCases: "You do not hold any case yet.",
  casesUnreadable: "The list of your cases could not be read. Try again in a few minutes.",
  allCases: "All cases",
  back: "Back to Home",
  claimedBy: "Claimed by",
  suppressed: "suppressed",
  utc: "UTC",
  /** A refusal of any kind is the words of a path nothing serves (rule 7: nothing says what was refused, or why). */
  notFound: { title: "Page not found", message: "That page could not be found." },
  unavailable: { title: "The alert queue is not available", message: "The alert queue cannot reach the service just now. Nothing has changed. Try again in a few minutes." },
  kinds: {
    hotlist: "Hotlist",
    monitor: "Watched pattern",
    analyst: "Raised by an analyst",
    drawn_watch: "A load met a drawn item",
  },
  /** An analyst's alert raised on a dataset (rule `analyst:dataset:…`): it reaches every case that reads the dataset, so it is not "raised by an analyst" in this case alone. */
  datasetAlert: "Dataset alert",
  /** What a typology alert is called when the typology is not one in `typologies` (or the Conduit names none): the React queue's own fallback. */
  typologyFallback: "Alert",
  states: { open: "Open", claimed: "Claimed", closing: "Closing", closed: "Closed" },
} as const;

/** The five kinds the route sends; a typology alert is named by its typology (below), the other four by `kinds`. */
const KIND_NAMES = ["typology", "hotlist", "monitor", "analyst", "drawn_watch"] as const;
type Kind = (typeof KIND_NAMES)[number];

/**
 * A copy of `TYPOLOGY_LABELS` in `packages/glass-shared/src/alerts/names.ts`, which the React queue names a typology alert by
 * (`typologyLabel`): this service imports no workspace package for it, so `alert-queue.test.ts` holds each key and the fallback to the
 * shared table. A typology the table does not have, or none, is "Alert", as in the React queue.
 */
const TYPOLOGIES: Readonly<Record<string, string>> = {
  structuring: "Structuring",
  rapid_movement: "Rapid movement",
  circular_flow: "Circular flow",
  kyc_screening: "KYC screening",
  shared_attributes: "Shared contact details",
  document_verification: "Unverified customer",
  pattern: "Drawn pattern",
  sentence: "Sentence rule",
  high_risk_jurisdiction: "High-risk jurisdiction",
  large_cash: "Large cash",
  dormant_reactivated: "Dormant account reactivated",
  velocity_rise: "Sudden rise in velocity",
};

/** A typology's name, as the React queue words it: its own, or "Alert" for one not named (or none). */
export function typologyWords(typology: string | null | undefined): string {
  return typeof typology === "string" && Object.hasOwn(TYPOLOGIES, typology) ? (TYPOLOGIES[typology] as string) : ALERT_QUEUE_WORDS.typologyFallback;
}

type State = keyof typeof ALERT_QUEUE_WORDS.states;

/** One row as the page draws it: five cells, each already words. */
export interface QueueRow {
  alert: string;
  kind: string;
  state: string;
  when: string;
  whenIso: string;
}

export interface CaseLink {
  name: string;
  href: string;
}

const DATASET_RULE = "analyst:dataset:";
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const two = (n: number): string => String(n).padStart(2, "0");

function isKind(value: unknown): value is Kind {
  return typeof value === "string" && (KIND_NAMES as readonly string[]).includes(value);
}

function isState(value: unknown): value is State {
  return typeof value === "string" && Object.hasOwn(ALERT_QUEUE_WORDS.states, value);
}

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

/** `24 November 2026, 09:15 UTC` and the same moment for a `datetime` attribute; undefined for text that is not a time. */
function whenOf(value: unknown): { words: string; iso: string } | undefined {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) return undefined;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return undefined;
  return {
    words: `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()] as string} ${at.getUTCFullYear()}, ${two(at.getUTCHours())}:${two(at.getUTCMinutes())} ${ALERT_QUEUE_WORDS.utc}`,
    iso: at.toISOString(),
  };
}

/** The Kind cell: the React queue's `alertTitle`. */
function kindWords(kind: Kind, typology: unknown, rule: unknown): string {
  if (kind === "typology") return typologyWords(typology as string | null);
  if (kind === "analyst") return (rule as string).startsWith(DATASET_RULE) ? ALERT_QUEUE_WORDS.datasetAlert : ALERT_QUEUE_WORDS.kinds.analyst;
  return ALERT_QUEUE_WORDS.kinds[kind];
}

/** One row of the route's list (`QueuedAlert`), or undefined when it is not what the route sends. */
function rowOf(item: unknown): QueueRow | undefined {
  if (!isObject(item)) return undefined;
  const alert = item["alert"];
  if (!isObject(alert)) return undefined;
  const { summary, kind, suppressed } = item;
  const state = alert["status"];
  const when = whenOf(alert["created_at"]);
  // The route always sends each of these, `assignee_name` as text or null: a missing one (undefined) is a body that is not the route's.
  if (typeof summary !== "string" || !isKind(kind) || typeof suppressed !== "boolean" || !isState(state) || when === undefined) return undefined;
  const holder = item["assignee_name"];
  if (holder !== null && typeof holder !== "string") return undefined;
  // What names the alert: the typology of a typology alert (text or null: the route always sends it) and the rule of an analyst's (text), as the React queue's `alertTitle`.
  const typology = alert["typology"];
  const rule = alert["rule_id"];
  if (kind === "typology" && typology !== null && typeof typology !== "string") return undefined;
  if (kind === "analyst" && typeof rule !== "string") return undefined;
  const base = state === "claimed" && holder !== null && holder !== "" ? `${ALERT_QUEUE_WORDS.claimedBy} ${holder}` : ALERT_QUEUE_WORDS.states[state];
  return {
    alert: summary,
    kind: kindWords(kind, typology, rule),
    state: suppressed ? `${base}, ${ALERT_QUEUE_WORDS.suppressed}` : base,
    when: when.words,
    whenIso: when.iso,
  };
}

/** The queue the Conduit sent, in the order it sent it; undefined when the body is not the route's list, or any row in it is not a row. */
export function queueRows(body: unknown): QueueRow[] | undefined {
  if (!Array.isArray(body)) return undefined;
  const rows: QueueRow[] = [];
  for (const item of body) {
    const row = rowOf(item);
    if (row === undefined) return undefined;
    rows.push(row);
  }
  return rows;
}

/** The cases the person holds, as the Conduit sent them (`id` and `name` of each); undefined when the body is not a list of them. */
export function caseList(body: unknown): { id: string; name: string }[] | undefined {
  if (!Array.isArray(body)) return undefined;
  const cases: { id: string; name: string }[] = [];
  for (const item of body) {
    if (!isObject(item) || typeof item["id"] !== "string" || typeof item["name"] !== "string") return undefined;
    cases.push({ id: item["id"], name: item["name"] });
  }
  return cases;
}

/** The name of the case with this id in a list that was read, or undefined (the page says "this case"). */
export function nameOfCase(cases: { id: string; name: string }[] | undefined, id: string): string | undefined {
  for (const item of cases ?? []) if (item.id === id) return item.name;
  return undefined;
}

export const QUEUE_PATH = "/alert-queue";

/** A link to a case's queue: the case's id as one encoded piece. */
export function caseLinks(cases: { id: string; name: string }[]): CaseLink[] {
  return cases.map((item) => ({ name: item.name, href: `${QUEUE_PATH}?case=${encodeURIComponent(item.id)}` }));
}
