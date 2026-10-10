// The events behind one link (ADR-089): the emails between two addresses, newest first, a page at
// a time. `GET .../links/{edge}/events` answers only to someone who can see the link, with the one
// `link_not_found` refusal for a hidden and a missing link alike.
import type { EventRecord, Node } from "../../../../packages/schemas/generated";

export const EVENTS_PAGE_SIZE = 50;

export interface LinkEventPage {
  total: number;
  offset: number;
  limit: number;
  events: EventRecord[];
}

export class LinkEventsError extends Error {
  kind: "link_not_found" | "forbidden" | "failed";
  constructor(kind: "link_not_found" | "forbidden" | "failed", message: string) {
    super(message);
    this.name = "LinkEventsError";
    this.kind = kind;
  }
}

export async function fetchLinkEvents(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  offset = 0,
  limit = EVENTS_PAGE_SIZE,
): Promise<LinkEventPage> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/` +
    `${encodeURIComponent(edgeId)}/events?offset=${offset}&limit=${limit}`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { Authorization: `Bearer ${bearerToken}` } });
  } catch {
    throw new LinkEventsError("failed", "The server could not be reached.");
  }
  if (!response.ok) {
    let body: { error?: string } = {};
    try {
      body = (await response.json()) as typeof body;
    } catch {
      // no body
    }
    if (body.error === "link_not_found") throw new LinkEventsError("link_not_found", "link not found");
    if (response.status === 403) throw new LinkEventsError("forbidden", "forbidden");
    throw new LinkEventsError("failed", `request failed: ${response.status}`);
  }
  return (await response.json()) as LinkEventPage;
}

/** What the section is called for this link: emails between two addresses, events otherwise.
 * Reads the ontology's own `Endpoint.endpoint_kind` from the link's source node, here and only
 * here, so no caller can read a different field (it read `kind`, which nothing carries). */
export type EventsNoun = "emails" | "messages" | "events";

/** Ends whose events are messages (ADR-094): a phone (number or SIM) or a messaging handle. */
const MESSAGE_ENDS = new Set(["msisdn", "imsi", "handle"]);

export function eventsNoun(edgeType: string, source: Node | undefined): EventsNoun {
  if (edgeType !== "COMMUNICATED_WITH") return "events";
  const kind = source?.properties?.endpoint_kind;
  if (kind === "email") return "emails";
  return typeof kind === "string" && MESSAGE_ENDS.has(kind) ? "messages" : "events";
}

/** The words for a noun: "Emails", "email". */
export function nounWords(noun: EventsNoun): { title: string; one: string; titleOne: string } {
  const one = noun === "emails" ? "email" : noun === "messages" ? "message" : "event";
  return { title: noun.charAt(0).toUpperCase() + noun.slice(1), one, titleOne: one.charAt(0).toUpperCase() + one.slice(1) };
}

/** Whether a link's events may carry text the canvas can show as Documents (ADR-092, ADR-094). */
export function mayCarryText(noun: EventsNoun): boolean {
  return noun === "emails" || noun === "messages";
}

/** The menu entry's label: "Show emails (12)". */
export function eventsEntryLabel(noun: EventsNoun, count: number): string {
  return `Show ${noun} (${count})`;
}

/** One of the model's findings for an email, pending until a person accepts or rejects it. */
export interface EmailCandidate {
  id: string;
  document_id: string;
  entity_type: string;
  properties: Record<string, unknown>;
  confidence: number;
  status: "pending" | "accepted" | "rejected";
  /** Who found it: "stanza:<version>", "analyst:<id>" for one marked by hand, or a model's name. */
  model?: string;
  /** Where in the source text it was found: `char span <start>-<end>` (`SourceRef.locator`). */
  locator?: string;
  /** sha256 of exactly the words the extractor matched there, so a locator is never trusted bare. */
  excerpt_hash?: string;
  node_id?: string | null;
}

export interface EmailExtraction {
  document_id: string;
  candidates: EmailCandidate[];
  delta: unknown;
}

export interface EmailAccept {
  node_id: string;
  delta: unknown;
}

async function post<T>(url: string, bearerToken: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new LinkEventsError("failed", "The server could not be reached.");
  }
  if (!response.ok) {
    let parsed: { error?: string; detail?: string } = {};
    try {
      parsed = (await response.json()) as typeof parsed;
    } catch {
      // no body
    }
    if (parsed.error === "link_not_found") throw new LinkEventsError("link_not_found", "link not found");
    if (response.status === 403) throw new LinkEventsError("forbidden", "forbidden");
    throw new LinkEventsError("failed", parsed.detail ?? `request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Asks for the entities in one email (ADR-089 step 3). The email becomes a Document node and the
 * findings come back pending; `delta` is what the working set gained. */
export async function extractEmail(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  eventId: string,
  using: ExtractUsing = "recogniser",
): Promise<EmailExtraction> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/` +
    `${encodeURIComponent(edgeId)}/events/${encodeURIComponent(eventId)}/extract`;
  return post<EmailExtraction>(url, bearerToken, { using });
}

/** Accepts one finding: an inferred node linked to the email, both into the working set. */
export async function acceptEmailCandidate(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  eventId: string,
  candidateId: string,
): Promise<EmailAccept> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/` +
    `${encodeURIComponent(edgeId)}/events/${encodeURIComponent(eventId)}/candidates/` +
    `${encodeURIComponent(candidateId)}/accept`;
  return post<EmailAccept>(url, bearerToken, {});
}

/** Rejects one finding (owner, 6 October 2026): marked rejected, nothing written. */
export async function rejectEmailCandidate(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  eventId: string,
  candidateId: string,
): Promise<void> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/` +
    `${encodeURIComponent(edgeId)}/events/${encodeURIComponent(eventId)}/candidates/` +
    `${encodeURIComponent(candidateId)}/reject`;
  await post<unknown>(url, bearerToken, {});
}

/** ADR-098: the fast recogniser (the default) or the language model on request. */
export type ExtractUsing = "recogniser" | "model";

/** Where a finding came from, as the list says it: the recogniser by name (it gives no score), a
 * hand-marking, or a model's confidence. */
export function candidateSource(candidate: EmailCandidate): string {
  const by = candidate.model ?? "";
  // A recogniser gives no score (ADR-098 Amendment 1 decision 3): its name shows instead of a
  // percentage. spaCy and the transformer recogniser joined Stanza with ADR-108 phase D.
  if (by.startsWith("stanza:")) return "found by Stanza";
  if (by.startsWith("spacy:")) return "found by spaCy";
  if (by.startsWith("transformers:")) return "found by the transformer recogniser";
  if (by.startsWith("analyst:")) return "marked by hand";
  return `${Math.round(candidate.confidence * 100)}%`;
}

/** Findings joined: those already listed kept as they are, new ones added after them. */
export function withNewFindings(listed: readonly EmailCandidate[], found: readonly EmailCandidate[]): EmailCandidate[] {
  const ids = new Set(listed.map((c) => c.id));
  return [...listed, ...found.filter((c) => !ids.has(c.id))];
}

/** How a finding reads in the list: "Person · MERCER, Dana". */
export function candidateLabel(candidate: EmailCandidate): string {
  const p = candidate.properties;
  const parts = [p.family_name, p.given_names, p.name, p.title, p.value_normalised, p.value]
    .filter((v): v is string => typeof v === "string" && v.trim() !== "");
  return `${candidate.entity_type} · ${parts.length > 0 ? parts.join(", ") : "(no name)"}`;
}
