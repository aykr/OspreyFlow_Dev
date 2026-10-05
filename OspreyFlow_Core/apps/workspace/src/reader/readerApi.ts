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
