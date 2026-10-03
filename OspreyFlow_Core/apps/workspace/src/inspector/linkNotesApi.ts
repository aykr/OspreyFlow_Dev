// Fetch wrappers for `GET/POST /v1/investigations/{id}/links/{edge}/notes` and
// `PUT/DELETE .../notes/{note}` (`services/api/link_notes.py`, ADR-075). Same conventions as
// `assessment/api.ts`: Bearer auth, throw on a non-`ok` response — here with a `LinkNotesError`
// that carries the server's own sentence and a `kind` the panel words its message from.
import type { LinkNote } from "../../../../packages/schemas/generated";

export type LinkNotesErrorKind =
  /** The link is not in this view, or the person may not see it — the server says one thing. */
  | "link_not_found"
  | "note_not_found"
  | "not_yours"
  | "invalid"
  /** A viewer-only case, or any other refusal. */
  | "forbidden"
  | "failed";

export class LinkNotesError extends Error {
  kind: LinkNotesErrorKind;
  constructor(kind: LinkNotesErrorKind, message: string) {
    super(message);
    this.name = "LinkNotesError";
    this.kind = kind;
  }
}

function headers(bearerToken: string, json = false): Record<string, string> {
  return json
    ? { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" }
    : { Authorization: `Bearer ${bearerToken}` };
}

function notesUrl(apiBaseUrl: string, investigationId: string, edgeId: string, noteId?: string) {
  const base = `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/${encodeURIComponent(edgeId)}/notes`;
  return noteId === undefined ? base : `${base}/${encodeURIComponent(noteId)}`;
}

async function refusal(response: Response): Promise<LinkNotesError> {
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // A non-JSON error body falls through to the generic kinds below.
  }
  if (body.error === "link_not_found") return new LinkNotesError("link_not_found", "link not found");
  if (body.error === "note_not_found") return new LinkNotesError("note_not_found", "note not found");
  if (body.error === "note_not_yours") {
    return new LinkNotesError("not_yours", body.detail ?? "That note is not yours.");
  }
  if (body.error === "invalid_note") {
    return new LinkNotesError("invalid", body.detail ?? "That note cannot be saved.");
  }
  if (response.status === 403) return new LinkNotesError("forbidden", "forbidden");
  return new LinkNotesError("failed", `request failed: ${response.status}`);
}

export async function listLinkNotes(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
): Promise<LinkNote[]> {
  const response = await fetch(notesUrl(apiBaseUrl, investigationId, edgeId), {
    headers: headers(bearerToken),
  });
  if (!response.ok) throw await refusal(response);
  return ((await response.json()) as { notes: LinkNote[] }).notes;
}

export async function addLinkNote(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  body: string,
): Promise<LinkNote> {
  const response = await fetch(notesUrl(apiBaseUrl, investigationId, edgeId), {
    method: "POST",
    headers: headers(bearerToken, true),
    body: JSON.stringify({ body }),
  });
  if (!response.ok) throw await refusal(response);
  return (await response.json()) as LinkNote;
}

export async function editLinkNote(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  noteId: string,
  body: string,
): Promise<LinkNote> {
  const response = await fetch(notesUrl(apiBaseUrl, investigationId, edgeId, noteId), {
    method: "PUT",
    headers: headers(bearerToken, true),
    body: JSON.stringify({ body }),
  });
  if (!response.ok) throw await refusal(response);
  return (await response.json()) as LinkNote;
}

export async function removeLinkNote(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  noteId: string,
): Promise<void> {
  const response = await fetch(notesUrl(apiBaseUrl, investigationId, edgeId, noteId), {
    method: "DELETE",
    headers: headers(bearerToken),
  });
  if (!response.ok) throw await refusal(response);
}
