// The links among nodes already in the view (ADR-098 decision 1): an expansion returns only the
// links it walked along, so the links between the nodes on screen are asked for separately.
// `POST .../links-among` adds all of them or, past the working set's cap, none (rule 2).
import type { WorkingSetDelta } from "../workingset/models";

const COUNT = new Intl.NumberFormat("en-GB");

export interface LinksAmongResult {
  added: number;
  delta: WorkingSetDelta;
}

/** The links among `nodeIds`, or among every node in the view when `null`. */
export async function showLinksAmong(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  nodeIds: readonly string[] | null,
): Promise<LinksAmongResult> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links-among`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ node_ids: nodeIds === null ? null : [...nodeIds] }),
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.ok) return (await response.json()) as LinksAmongResult;
  let body: { error?: string; cap_kind?: string; cap?: number; would_be?: number } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // no body
  }
  if (body.error === "limit_exceeded" && body.cap !== undefined && body.would_be !== undefined) {
    throw new Error(
      `Too many for the canvas: ${COUNT.format(body.would_be)} ${body.cap_kind ?? "edges"} ` +
        `against a limit of ${COUNT.format(body.cap)}. Select fewer nodes and try again.`,
    );
  }
  if (response.status === 403) throw new Error("Changing this case needs Editor access.");
  throw new Error(`Showing the links failed (${response.status}). Try again.`);
}

/** What the analyst is told once the links are drawn. */
export function linksAmongNotice(added: number): string {
  if (added === 0) return "No more links among these.";
  return `${COUNT.format(added)} ${added === 1 ? "link" : "links"} added among these.`;
}

/** What an expansion says about the links among its nodes and the view (`ExpansionOutcome`). */
export function expansionLinksNotice(linksAmong: string | undefined): string | null {
  if (linksAmong !== "view_full") return null;
  return (
    "The links among these and the rest of the view were not added: there would be too many. " +
    "Select fewer and use Show links among these."
  );
}
