// Fetch wrappers for `POST /v1/investigations/{id}/links/{edge}/change` and `GET .../history`
// (`services/api/link_changes.py`, ADR-080). Same conventions as `linkNotesApi.ts`: Bearer auth,
// throw on a refusal with the server's own sentence and a `kind` the form words its message from.
// The shapes are written out here because they are not domain models (`schemas/generated` holds
// only those); they mirror `LinkChange`, `LinkChangeRequest` and `LinkChangeResult` in the server.
import type { Edge, Handling } from "../../../../packages/schemas/generated";
import type { DeltaReplaceEdge } from "../workingset/models";

export interface LinkChangeRecord {
  id: string;
  investigation_id: string;
  /** The link this change produced. */
  edge_id: string;
  /** The link it replaced. */
  previous_edge_id: string;
  changed_by: string;
  changed_at: string;
  reason: string;
  /** The type, properties, validity period and records behind the link, as they were … */
  before: LinkSnapshot;
  /** … and as they became. */
  after: LinkSnapshot;
}

export interface LinkSnapshot {
  type: string;
  properties: Record<string, unknown>;
  interval: { valid_from: string; valid_to: string | null } | null;
  occurrences: number;
  /** ADR-102: recorded on changes made since handling could be changed; absent on older ones. */
  handling?: Handling;
}

export interface LinkChangeInput {
  /** Required: why the link is being changed. */
  reason: string;
  type?: string;
  properties?: Record<string, unknown>;
  /** `null` clears the validity period; leaving the field out leaves it alone. */
  interval?: { valid_from: string; valid_to: string | null } | null;
  occurrences?: number;
  /** What stands behind the link (ADR-081 step B). Left out, the link keeps what stood behind it. */
  basis?: "direct" | "probabilistic";
  /** ADR-102: the link's handling. Left out, it is kept. */
  handling?: Handling;
  /** ADR-102: sent with a lower handling, which an Author must confirm. */
  confirm_lower?: boolean;
}

export interface LinkChangeResult {
  edge: Edge;
  delta: DeltaReplaceEdge;
  change: LinkChangeRecord;
}

export interface LinkHistory {
  changes: LinkChangeRecord[];
  truncated: boolean;
}

export type LinkChangeErrorKind =
  /** The link is not in this view, or the person may not see it — the server says one thing. */
  | "link_not_found"
  /** The reason is missing, or the ontology refuses the change. The message is the server's. */
  | "invalid"
  | "nothing_changed"
  /** A same-as or not-the-same link: confirmed or marked, not edited. */
  | "resolution_link"
  /** ADR-102: lowering a link's handling needs Author access. */
  | "lowering_needs_author"
  /** ADR-102: a lower handling was sent without the confirmation. */
  | "confirm_lower"
  | "forbidden"
  | "failed";

export class LinkChangeError extends Error {
  kind: LinkChangeErrorKind;
  constructor(kind: LinkChangeErrorKind, message: string) {
    super(message);
    this.name = "LinkChangeError";
    this.kind = kind;
  }
}

function linkUrl(apiBaseUrl: string, investigationId: string, edgeId: string, tail: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/${encodeURIComponent(edgeId)}/${tail}`;
}

async function refusal(response: Response): Promise<LinkChangeError> {
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // A non-JSON error body falls through to the generic kinds below.
  }
  if (body.error === "link_not_found") return new LinkChangeError("link_not_found", "link not found");
  if (body.error === "invalid_link_change") {
    return new LinkChangeError("invalid", body.detail ?? "That change cannot be saved.");
  }
  if (body.error === "nothing_changed") {
    return new LinkChangeError("nothing_changed", body.detail ?? "Nothing about the link would change.");
  }
  if (body.error === "resolution_link") {
    return new LinkChangeError("resolution_link", body.detail ?? "Same-as links are not edited.");
  }
  if (body.error === "lowering_needs_author") {
    return new LinkChangeError("lowering_needs_author", "Lowering a link's handling needs Author access.");
  }
  if (body.error === "confirm_lower_handling") {
    return new LinkChangeError("confirm_lower", body.detail ?? "Confirm that you mean to lower the handling.");
  }
  if (response.status === 403) return new LinkChangeError("forbidden", "forbidden");
  return new LinkChangeError("failed", `request failed: ${response.status}`);
}

async function send(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new LinkChangeError("failed", "The server could not be reached.");
  }
}

export async function changeLink(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  input: LinkChangeInput,
): Promise<LinkChangeResult> {
  const response = await send(linkUrl(apiBaseUrl, investigationId, edgeId, "change"), {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await refusal(response);
  return (await response.json()) as LinkChangeResult;
}

export async function fetchLinkHistory(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
): Promise<LinkHistory> {
  const response = await send(linkUrl(apiBaseUrl, investigationId, edgeId, "history"), {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw await refusal(response);
  const body = (await response.json()) as Partial<LinkHistory> | null;
  // An answer that is not a history is a failure to load one, not an empty history.
  if (!body || !Array.isArray(body.changes)) {
    throw new LinkChangeError("failed", "The server's answer was not a history.");
  }
  return { changes: body.changes, truncated: body.truncated === true };
}
