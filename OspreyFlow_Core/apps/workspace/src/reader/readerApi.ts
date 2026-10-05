// The full-screen reader's text (ADR-092): `GET .../documents/{id}/reader` answers only to someone
// who can see the Document in the case, with one `document_not_found` for hidden and missing alike.
import type { MessageSpan } from "../dossier/models";

/** `services/api/document_reader.py`'s `DocumentReaderView`. */
export interface DocumentReaderView {
  document_id: string;
  title: string | null;
  text: string;
  truncated: boolean;
  spans: MessageSpan[];
  sent_at: string | null;
  sender_id: string | null;
  recipient_id: string | null;
  edge_id: string | null;
  event_id: string | null;
  /** ADR-094: `text`, `image` or `video` for a Document written from held content. */
  media_kind?: string | null;
  /** The Document has a file in the media store, fetched by `fetchDocumentFile`. */
  has_file?: boolean;
}

function documentUrl(apiBaseUrl: string, investigationId: string, documentId: string): string {
  return (
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/documents/` +
    encodeURIComponent(documentId)
  );
}

/** A held Document's file, as a URL an `<img>` or `<video>` can show (it needs the analyst's token,
 * which an element's own request cannot carry). The caller revokes it. */
export async function fetchDocumentFile(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  documentId: string,
): Promise<string> {
  const response = await fetch(`${documentUrl(apiBaseUrl, investigationId, documentId)}/file`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw new Error("The file could not be opened.");
  return URL.createObjectURL(await response.blob());
}

export interface DocumentFinding {
  id: string;
  document_id: string;
  entity_type: string;
  properties: Record<string, unknown>;
  confidence: number;
  status: "pending" | "accepted" | "rejected";
}

async function postJson<T>(url: string, bearerToken: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: "{}",
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.status === 403) throw new Error("This needs Editor access to the case.");
  if (response.status === 404) throw new Error("This document is not in your view.");
  if (!response.ok) throw new Error(`The request failed (${response.status}).`);
  return (await response.json()) as T;
}

/** Entities from a held Document by its kind: text, an image described and read, a video
 * transcribed (ADR-094). Findings are pending until accepted. */
export function extractDocument(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  documentId: string,
): Promise<{ document_id: string; text: string; candidates: DocumentFinding[] }> {
  return postJson(`${documentUrl(apiBaseUrl, investigationId, documentId)}/extract`, bearerToken);
}

export function acceptDocumentFinding(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  documentId: string,
  candidateId: string,
): Promise<{ node_id: string; delta: unknown }> {
  return postJson(
    `${documentUrl(apiBaseUrl, investigationId, documentId)}/candidates/${encodeURIComponent(candidateId)}/accept`,
    bearerToken,
  );
}

/** The id an email's Document is written under: the server's `email_document_id`. */
export function emailDocumentId(eventId: string): string {
  return `email:${eventId}`;
}

export async function fetchDocumentReader(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  documentId: string,
): Promise<DocumentReaderView> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/documents/` +
    `${encodeURIComponent(documentId)}/reader`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { Authorization: `Bearer ${bearerToken}` } });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.status === 404) throw new Error("This document is not in your view.");
  if (!response.ok) throw new Error(`The document could not be opened (${response.status}).`);
  return (await response.json()) as DocumentReaderView;
}
