// The emails behind a link onto the canvas (ADR-092): `POST .../links/{edge}/events/documents`
// writes each email inside the brushed window as a Document linked to both addresses, all or
// none against the working set's cap, and answers with the delta that draws them.
import type { WorkingSetDelta } from "../workingset/models";

export interface EmailDocumentsResult {
  written: number;
  /** -1 when none of the link's events had text (`not_documents`), which is not a failure. */
  without_text: number;
  /** `null` when nothing was written. */
  delta: WorkingSetDelta | null;
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
  // A phone link of calls has events but no text: said as a notice, not raised as a failure.
  if (body.error === "not_documents") return { written: 0, without_text: -1, delta: null };
  if (body.error === "link_not_found") throw new Error("This link is no longer in the view.");
  if (response.status === 403) throw new Error("Changing this case needs Editor access.");
  throw new Error(`Showing the emails failed (${response.status}). Try again.`);
}

/** What the analyst is told once the emails or messages are on the canvas. `withoutText` of -1
 * means none of the link's events had text (the server's `not_documents`). */
export function emailsOutcomeText(
  written: number,
  withoutText: number,
  noun: "emails" | "messages" = "emails",
): string {
  if (withoutText < 0) return "None of these has text to show as a document.";
  const one = noun === "emails" ? "email" : "message";
  if (written === 0 && withoutText === 0) return `No ${noun} in the timeline's window.`;
  const shown = `${COUNT.format(written)} ${written === 1 ? one : noun} put on the canvas`;
  if (withoutText === 0) return `${shown}.`;
  return `${shown}; ${COUNT.format(withoutText)} ${withoutText === 1 ? "event" : "events"} had no text.`;
}
