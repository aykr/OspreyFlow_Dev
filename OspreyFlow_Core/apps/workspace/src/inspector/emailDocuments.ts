// The emails behind a link onto the canvas (ADR-092): `POST .../links/{edge}/events/documents`
// writes each email inside the brushed window as a Document linked to both addresses, all or
// none against the working set's cap, and answers with the delta that draws them.
import type { WorkingSetDelta } from "../workingset/models";

export interface EmailDocumentsResult {
  written: number;
  without_text: number;
  delta: WorkingSetDelta;
}

const COUNT = new Intl.NumberFormat("en-GB");

export async function showEmailsAsDocuments(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeId: string,
  window: { validFrom: string; validTo: string | null } | null,
): Promise<EmailDocumentsResult> {
  const url =
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links/` +
    `${encodeURIComponent(edgeId)}/events/documents`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        window: window ? { valid_from: window.validFrom, valid_to: window.validTo } : null,
      }),
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.ok) return (await response.json()) as EmailDocumentsResult;
  let body: { error?: string; cap_kind?: string; cap?: number; would_be?: number } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // no body
  }
  if (body.error === "limit_exceeded" && body.cap !== undefined && body.would_be !== undefined) {
    throw new Error(
      `Too many for the canvas: ${COUNT.format(body.would_be)} ${body.cap_kind ?? "nodes"} ` +
        `against a limit of ${COUNT.format(body.cap)}. Narrow the timeline and try again.`,
    );
  }
  if (body.error === "not_documents") {
    throw new Error("These events have no text, so none can be shown as a document.");
  }
  if (body.error === "link_not_found") throw new Error("This link is no longer in the view.");
  if (response.status === 403) throw new Error("Changing this case needs Editor access.");
  throw new Error(`Showing the emails failed (${response.status}). Try again.`);
}

/** What the analyst is told once the emails are on the canvas. */
export function emailsOutcomeText(written: number, withoutText: number): string {
  if (written === 0 && withoutText === 0) return "No emails in the timeline's window.";
  const emails = `${COUNT.format(written)} ${written === 1 ? "email" : "emails"} put on the canvas`;
  if (withoutText === 0) return `${emails}.`;
  return `${emails}; ${COUNT.format(withoutText)} ${withoutText === 1 ? "event" : "events"} had no text.`;
}
