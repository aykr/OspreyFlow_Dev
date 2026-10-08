// The Explore panel's reads (ADR-100): what the case's data holds, and its most connected nodes.
// Both are under `/v1/investigations/{id}/explore/`, so each figure is of the case's datasets and
// the analyst's clearance, counted in the store; nothing here widens or reckons them again.
import type {
  Groups,
  BusiestDays,
  RankedLinks,
  RankedNodes,
  TypeCounts,
} from "../../../../packages/schemas/generated";

export type {
  Bridge,
  Group,
  Groups,
  BusiestDays,
  BusyDay,
  RankedLink,
  RankedLinks,
  RankedNode,
  RankedNodes,
  TypeCounts,
} from "../../../../packages/schemas/generated";

function exploreUrl(apiBaseUrl: string, investigationId: string, path: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/explore/${path}`;
}

async function get<T>(url: string, bearerToken: string, what: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { headers: { Authorization: `Bearer ${bearerToken}` } });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (!response.ok) throw new Error(`${what} could not be read (${response.status}).`);
  return (await response.json()) as T;
}

export function loadTypeCounts(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<TypeCounts> {
  return get(exploreUrl(apiBaseUrl, investigationId, "counts"), bearerToken, "What this case holds");
}

export interface RankingPage {
  entityType?: string;
  limit?: number;
  offset?: number;
}

export function loadMostConnected(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  { entityType, limit = 10, offset = 0 }: RankingPage,
): Promise<RankedNodes> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (entityType) query.set("entity_type", entityType);
  return get(
    exploreUrl(apiBaseUrl, investigationId, `most-connected?${query.toString()}`),
    bearerToken,
    "The most connected",
  );
}

export function loadBusiestLinks(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  { limit = 10, offset = 0 }: RankingPage,
): Promise<RankedLinks> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return get(
    exploreUrl(apiBaseUrl, investigationId, `busiest-links?${query.toString()}`),
    bearerToken,
    "The busiest links",
  );
}

export function loadBusiestDays(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  { limit = 10, offset = 0 }: RankingPage,
): Promise<BusiestDays> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return get(
    exploreUrl(apiBaseUrl, investigationId, `busiest-days?${query.toString()}`),
    bearerToken,
    "The busiest days",
  );
}

/** The case's groups and bridges (ADR-100 decision 6). A case over the working set's caps is
 * answered `limit_exceeded`, said here in words with both figures. */
export async function loadGroups(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Groups> {
  let response: Response;
  try {
    response = await fetch(exploreUrl(apiBaseUrl, investigationId, "groups"), {
      headers: { Authorization: `Bearer ${bearerToken}` },
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.status === 409) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: string;
      cap_kind?: string;
      cap?: number;
      would_be?: number;
    };
    if (body.error === "limit_exceeded") {
      const fmt = new Intl.NumberFormat("en-GB");
      const what = body.cap_kind === "edges" ? "links" : "nodes";
      throw new Error(
        `Too large to group here: ${fmt.format(body.would_be ?? 0)} ${what}, more than ${fmt.format(body.cap ?? 0)}.`,
      );
    }
  }
  if (!response.ok) throw new Error(`The groups could not be read (${response.status}).`);
  return (await response.json()) as Groups;
}
