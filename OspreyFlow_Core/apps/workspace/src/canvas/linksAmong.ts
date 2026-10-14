// The links among nodes already in the view (ADR-098 decision 1): an expansion returns only the
// links it walked along, so the links between the nodes on screen are asked for separately.
// `POST .../links-among` adds all of them or, past the working set's cap, none (rule 2).
import type { WorkingSetDelta } from "../workingset/models";

const COUNT = new Intl.NumberFormat("en-GB");

export interface LinksAmongRoutes {
  degree: number;
  added_nodes: number;
  unconnected_pairs: number;
  more_routes_pairs: number;
}

export interface LinksAmongResult extends Partial<LinksAmongRoutes> {
  added: number;
  delta: WorkingSetDelta;
}

/** The links among `nodeIds`, or among every node in the view when `null` — and, past one degree
 * (ADR-098 Amendment 4), the routes between the selected nodes within that many degrees. */
export async function showLinksAmong(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  nodeIds: readonly string[] | null,
  degree = 1,
): Promise<LinksAmongResult> {
  let response: Response;
  try {
    response = await fetch(
      `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/links-among`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${bearerToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          node_ids: nodeIds === null ? null : [...nodeIds],
          ...(degree > 1 ? { degree } : {}),
        }),
      },
    );
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.ok) return (await response.json()) as LinksAmongResult;
  let body: {
    error?: string;
    cap_kind?: string;
    cap?: number;
    would_be?: number;
    detail?: { msg?: string }[];
  } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // no body
  }
  if (
    body.error === "limit_exceeded" &&
    body.cap !== undefined &&
    body.would_be !== undefined
  ) {
    throw new Error(
      `Too many for the canvas: ${COUNT.format(body.would_be)} ${body.cap_kind ?? "edges"} ` +
        `against a limit of ${COUNT.format(body.cap)}. Select fewer nodes and try again.`,
    );
  }
  if (response.status === 403)
    throw new Error("Changing this case needs Editor access.");
  // A request the server refuses before asking the store (Amendment 4): its own words.
  const said =
    response.status === 422
      ? body.detail?.[0]?.msg?.replace(/^Value error, /, "")
      : undefined;
  if (said) throw new Error(`${said.charAt(0).toUpperCase()}${said.slice(1)}.`);
  throw new Error(`Showing the links failed (${response.status}). Try again.`);
}

const plural = (n: number, one: string, many: string) =>
  `${COUNT.format(n)} ${n === 1 ? one : many}`;

/** What the analyst is told once the links are drawn; past one degree, what the routes added, the
 * pairs no route joins, and the pairs with more routes than were drawn (said, never hidden). */
export function linksAmongNotice(
  added: number,
  routes?: LinksAmongRoutes,
): string {
  if (!routes || routes.degree <= 1) {
    if (added === 0) return "No more links among these.";
    return `${plural(added, "link", "links")} added among these.`;
  }
  const within = `within ${routes.degree} degrees`;
  const said = [
    added === 0 && routes.added_nodes === 0
      ? `No routes ${within} among these.`
      : `${plural(added, "link", "links")} and ${plural(routes.added_nodes, "node", "nodes")} added: ` +
        `the routes ${within} among these.`,
  ];
  if (routes.unconnected_pairs > 0) {
    said.push(
      `${plural(routes.unconnected_pairs, "pair is", "pairs are")} not connected ${within}.`,
    );
  }
  if (routes.more_routes_pairs > 0) {
    said.push(
      `${plural(routes.more_routes_pairs, "pair has", "pairs have")} more routes than were drawn: ` +
        "Find connections lists them all.",
    );
  }
  return said.join(" ");
}

/** What an expansion says about the links among its nodes and the view (`ExpansionOutcome`). */
export function expansionLinksNotice(
  linksAmong: string | undefined,
): string | null {
  if (linksAmong !== "view_full") return null;
  return (
    "The links among these and the rest of the view were not added: there would be too many. " +
    "Select fewer and use Show links among these."
  );
}
