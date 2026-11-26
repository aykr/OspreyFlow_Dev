/**
 * The reader page's words and the view it is drawn from (slice GG3b; ADR-152 decisions 5, 6 and 12; FUNCTIONS row `documents`;
 * scenario DR). Nothing here is a call or a right: a word, or a function from what the Conduit answered to what the template draws.
 *
 * **The strict reader.** A body is read field by field against the route's models: `DocumentReaderView`
 * (`services/api/document_reader.py`) and `MessageSpan` (`services/api/dossier.py`). Every field the route sends (`REQUIRED`; FastAPI
 * sends a field's default too) must be there, of its type; a body missing one, or with one of another shape, is not a view
 * (`undefined`), said as "could not be read", never as an empty text or an empty table (rule 2). So is a span the page cannot place:
 * one outside the text, one that ends where it starts or before, and spans out of the route's order (`get_document_view` sorts them by
 * their start), since a mark drawn from any of them would mark other words than the span's.
 * **The field census.** `CENSUS` names, for each model, the fields the page draws and the fields it leaves out; Scenario DR's "Left out,
 * by field name" sentence names the same, and `tests/glass_trees/test_govuk_document_scenario.py` holds both to the models' own fields.
 *
 * **Places are characters as the Conduit counts them.** A span's `start` and `end` are Python string indices: code points, where a
 * JavaScript string counts UTF-16 units, so a character outside the basic plane (an emoji) would move every later mark by one. The text
 * is read as its code points (`Array.from`) and every place is counted in them.
 *
 * **The marks.** Each span is one row of the table, in the order sent, its own words (rule 5: "Proposed by a model, not yet confirmed"
 * for an inferred span, never drawn as confirmed). In the text, spans that overlap are one marked passage over both, so no word is
 * drawn twice and none is lost; spans that only touch stay two. Nothing here removes, cuts, sorts or counts a span (decision 5; rule 3
 * stays with the Conduit: the route already leaves out a span whose node the reader may not see). Plain words, British English.
 *
 * **The file** is chosen by `media_kind` when `has_file` is true (the owner's ruling 6 (a)): a picture is an `<img>`, a film a
 * `<video controls>`, any other file a link, never shown. Its address is the page service's own `/v1` forwarder's path for the file, so
 * it is the same origin and carries the person's bearer there; the browser's load of it is a second read the Conduit audits itself.
 */

export const DOCUMENT_WORDS = {
  about: "A document",
  untitled: "A document with no title",
  sentOn: (iso: string): string => `Sent on ${moment(iso)}`,
  fileHeading: "The document's file",
  picture: "A picture from the document",
  film: "A film from the document",
  openFile: "Open the document's file",
  textHeading: "The document's text",
  truncated: "This is the start of the message: the rest was not loaded.",
  noText: "This document has no text to show.",
  marksHeading: "Words marked in it",
  caption: "Words marked in the document's text",
  columns: ["Words", "Type", "How it was marked"],
  noMarks: "No words are marked in this document.",
  provenance: {
    asserted: "Marked by a person",
    inferred: "Proposed by a model, not yet confirmed",
    unresolved: "From a single source, not yet corroborated",
  },
  unreadable: "This document could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  toCase: "Back to the case",
  back: "Back to Home",
} as const;

/** Each model the page reads: the fields it draws and the fields it leaves out (Scenario DR names the same). */
export const CENSUS = {
  DocumentReaderView: { drawn: ["title", "text", "truncated", "spans", "sent_at", "media_kind", "has_file"], left: ["document_id", "sender_id", "recipient_id", "edge_id", "event_id"] },
  MessageSpan: { drawn: ["start", "end", "entity_type", "provenance_state"], left: ["node_id"] },
} as const;

type Model = keyof typeof CENSUS;

/** Every field each model sends: the strict reader asks for each one (no field of either is `exclude=True`; the scenario test holds that). */
export const REQUIRED = Object.fromEntries(Object.entries(CENSUS).map(([model, { drawn, left }]) => [model, [...drawn, ...left]])) as Record<Model, string[]>;

// The values a span's provenance may take: the model's own (`ProvenanceState`, `packages/schemas/domain.py`), which
// `tests/glass_trees/test_govuk_document_scenario.py` holds this list to, so a state added to the model fails that test first.
export const PROVENANCE_STATES = ["asserted", "inferred", "unresolved"] as const;

type Provenance = (typeof PROVENANCE_STATES)[number];

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** A moment as the reader says it: "3 March 2026 at 14:05 UTC". Written by hand, not by Intl, so it is the same on every engine. */
function moment(iso: string): string {
  const at = new Date(iso);
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()] ?? ""} ${at.getUTCFullYear()} at ${two(at.getUTCHours())}:${two(at.getUTCMinutes())} UTC`;
}

/** A run of the text: its lines (a line break is drawn as one), and whether it is a marked passage. */
export interface Piece {
  marked: boolean;
  lines: string[];
}

export interface MarkRow {
  lines: string[];
  type: string;
  how: string;
}

export type FileView = { kind: "picture" | "film" | "link"; src: string } | undefined;

export interface DocumentView {
  kind: "document";
  title: string;
  sent: string | undefined;
  file: FileView;
  truncated: boolean;
  pieces: Piece[];
  rows: MarkRow[];
  caseHref: string;
}

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";
const isTextOrNull = (value: unknown): value is string | null => value === null || isText(value);
const isPlace = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
const isProvenance = (value: unknown): value is Provenance => PROVENANCE_STATES.some((state) => state === value);
/** A moment the page can say: a time that does not parse is a body the page does not draw from. */
const isTimeOrNull = (value: unknown): value is string | null => value === null || (isText(value) && !Number.isNaN(new Date(value).getTime()));

// No separate presence check: each field is checked for its type below, and `undefined` is no field's type (the optional ones are a
// value or `null`), so a missing field is refused by the same check as a wrong one, as GR1a's reader found (rule 15).

interface ReadSpan {
  start: number;
  end: number;
  entity_type: string;
  provenance_state: Provenance;
}

/** One span, read strictly; `undefined` when it is not one. */
function spanOf(body: unknown): ReadSpan | undefined {
  if (!isObject(body)) return undefined;
  const { start, end, node_id, entity_type, provenance_state } = body;
  if (!isPlace(start) || !isPlace(end) || !isText(node_id) || !isText(entity_type) || !isProvenance(provenance_state)) return undefined;
  return { start, end, entity_type, provenance_state };
}

/** The words from `from` up to `to` (code points), as lines. */
function linesOf(chars: readonly string[], from: number, to: number): string[] {
  const lines: string[] = [""];
  for (let at = from; at < to; at += 1) {
    const char = chars[at] as string;
    if (char === "\n") lines.push("");
    else lines[lines.length - 1] += char;
  }
  return lines;
}

/** The address of the page of a document of a case: one page with both in its query (a page's path is a plain path: `pages.ts`). */
export const documentHref = (caseId: string, documentId: string): string => `/cases/document?case=${encodeURIComponent(caseId)}&document=${encodeURIComponent(documentId)}`;
/** The page service's own forwarder's path for the document's file (`GET /v1/investigations/{id}/documents/{document_id}/file`). */
export const fileHref = (caseId: string, documentId: string): string =>
  `/v1/investigations/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/file`;
/** GR1a's page of the case. */
const caseHref = (caseId: string): string => `/cases?case=${encodeURIComponent(caseId)}`;

/**
 * The page's view of `GET .../documents/{documentId}/reader`'s answer, for the case and the document of the address; `undefined` when
 * the body is not the route's, or holds a span the page cannot place (said as could not be read).
 */
export function documentView(caseId: string, documentId: string, body: unknown): DocumentView | undefined {
  if (!isObject(body)) return undefined;
  const { document_id, title, text, truncated, spans, sent_at, sender_id, recipient_id, edge_id, event_id, media_kind, has_file } = body;
  if (!isText(document_id) || !isTextOrNull(title) || !isText(text) || typeof truncated !== "boolean" || !Array.isArray(spans)) return undefined;
  if (!isTimeOrNull(sent_at) || !isTextOrNull(sender_id) || !isTextOrNull(recipient_id) || !isTextOrNull(edge_id) || !isTextOrNull(event_id)) return undefined;
  if (!isTextOrNull(media_kind) || typeof has_file !== "boolean") return undefined;

  const chars = Array.from(text);
  const read: ReadSpan[] = [];
  let lastStart = 0;
  for (const item of spans as unknown[]) {
    const one = spanOf(item);
    // A span the page cannot place: outside the text, empty or backwards, or out of the route's order.
    if (one === undefined || one.end > chars.length || one.end <= one.start || one.start < lastStart) return undefined;
    lastStart = one.start;
    read.push(one);
  }

  // The marked passages: overlapping spans joined, touching ones kept apart, in the order of the text.
  const passages: { start: number; end: number }[] = [];
  for (const one of read) {
    const last = passages[passages.length - 1];
    if (last !== undefined && one.start < last.end) last.end = Math.max(last.end, one.end);
    else passages.push({ start: one.start, end: one.end });
  }
  const pieces: Piece[] = [];
  let cursor = 0;
  for (const passage of passages) {
    if (passage.start > cursor) pieces.push({ marked: false, lines: linesOf(chars, cursor, passage.start) });
    pieces.push({ marked: true, lines: linesOf(chars, passage.start, passage.end) });
    cursor = passage.end;
  }
  if (cursor < chars.length) pieces.push({ marked: false, lines: linesOf(chars, cursor, chars.length) });

  const src = fileHref(caseId, documentId);
  const file: FileView = !has_file ? undefined : media_kind === "image" ? { kind: "picture", src } : media_kind === "video" ? { kind: "film", src } : { kind: "link", src };
  return {
    kind: "document",
    // An empty title is no title: a heading with no words is no heading.
    title: title === null || title.trim() === "" ? DOCUMENT_WORDS.untitled : title,
    sent: sent_at === null ? undefined : DOCUMENT_WORDS.sentOn(sent_at),
    file,
    truncated,
    pieces,
    rows: read.map((one) => ({ lines: linesOf(chars, one.start, one.end), type: one.entity_type, how: DOCUMENT_WORDS.provenance[one.provenance_state] })),
    caseHref: caseHref(caseId),
  };
}
