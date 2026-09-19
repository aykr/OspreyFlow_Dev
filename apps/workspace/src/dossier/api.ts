import type { DocumentView } from "./models";

/**
 * `null` on a non-2xx response — a document with no persisted text (nothing ran extraction
 * against it, or it predates Stage 4's own `document_texts` table) or one this principal cannot
 * see is a legitimate, ordinary state here, not an error to surface: `Dossier.tsx` simply omits
 * it rather than distinguishing "doesn't exist" from "exists but hidden," the same existence-leak
 * discipline the backend response itself already observes for individual spans.
 */
export async function fetchDocumentView(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  documentId: string,
): Promise<DocumentView | null> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/dossier/documents/${documentId}`,
    { headers: { Authorization: `Bearer ${bearerToken}` } },
  );
  if (!response.ok) return null;
  return (await response.json()) as DocumentView;
}
