// The events behind one link (ADR-089): the emails between two addresses, newest first, a page at
// a time. `GET .../links/{edge}/events` answers only to someone who can see the link, with the one
// `link_not_found` refusal for a hidden and a missing link alike.
import type { EventRecord } from "../../../../packages/schemas/generated";

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

/** What the section is called for this link: emails between two addresses, events otherwise. */
export function eventsNoun(edgeType: string, sourceKind: string | undefined): "emails" | "events" {
  return edgeType === "COMMUNICATED_WITH" && sourceKind === "email" ? "emails" : "events";
}

/** The menu entry's label: "Show emails (12)". */
export function eventsEntryLabel(noun: "emails" | "events", count: number): string {
  return `Show ${noun} (${count})`;
}
