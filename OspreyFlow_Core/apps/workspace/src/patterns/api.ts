// Fetch wrappers for `POST /v1/patterns/preview`, `POST /v1/patterns/run` and the saved-pattern
// routes (`services/api/patterns.py`, `services/api/pattern_store.py`) — mirrors `metrics/api.ts`'s
// own conventions. Preview and run are asked of the case, since a case reads only its own datasets
// (ADR-099); saved patterns are the analyst's, not a case's. `06_DECISIONS.md` ADR-032/036/040: save/load/list only —
// no share endpoint exists, since ADR-040 (pattern sharing) is Proposed, not accepted.
import type { PatternQuery, SavedPattern, Subgraph } from "../../../../packages/schemas/generated";

export interface PatternPreview {
  estimated_count: number;
  is_floor: boolean;
}

export interface PatternRunAccepted {
  mode: "sync" | "job";
  subgraph?: Subgraph | null;
  matched_count?: number | null;
  job_id?: string | null;
}

/** ADR-129 decision 2: what ask to search answers before anything runs. The pattern is the
 * builder's own `PatternQuery`, with the analyst's selection already resolved into its pinned
 * nodes; the count is the preview route's own. */
export interface PatternProposal {
  pattern: PatternQuery;
  explanation: string;
  estimated_count: number;
  is_floor: boolean;
}

/** ADR-121: a condition the ontology refuses comes back as a typed 422
 * (`pattern_condition_refused`, with its reason in words); the analyst is shown those words. ADR-129:
 * a question that cannot be drawn comes back as `could_not_express`, and the panel says so. Any
 * other failure keeps the status-only message it always had. */
async function failure(response: Response, fallback: string): Promise<Error> {
  try {
    const body = (await response.json()) as { error?: unknown; detail?: unknown };
    if (body.error === "pattern_condition_refused" && typeof body.detail === "string") {
      return new Error(body.detail);
    }
    if (body.error === "could_not_express") {
      const why = typeof body.detail === "string" ? ` ${body.detail}` : "";
      return new Error(`Could not express the question as a pattern.${why}`);
    }
  } catch {
    // Not JSON: the status is all there is to say.
  }
  return new Error(fallback);
}

function caseUrl(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`;
}

export async function fetchPatternPreview(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  pattern: PatternQuery,
): Promise<PatternPreview> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/patterns/preview`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(pattern),
  });
  if (!response.ok) {
    throw await failure(response, `POST /v1/patterns/preview failed: ${response.status}`);
  }
  return (await response.json()) as PatternPreview;
}

export async function runPattern(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  pattern: PatternQuery,
): Promise<PatternRunAccepted> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/patterns/run`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(pattern),
  });
  if (!response.ok) {
    throw await failure(response, `POST /v1/patterns/run failed: ${response.status}`);
  }
  return (await response.json()) as PatternRunAccepted;
}

/** ADR-129 decision 2: asks the model to propose a pattern for a question, in the case's own
 * vocabulary. The model is sent only the vocabulary and the question; `selectedNodeIds` are
 * resolved by the Conduit, to nodes the analyst may see, and never reach it. Nothing runs. */
export async function askToSearch(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  question: string,
  selectedNodeIds: readonly string[],
): Promise<PatternProposal> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/patterns/ask`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ question, selected_node_ids: selectedNodeIds }),
  });
  if (!response.ok) {
    throw await failure(response, `POST .../patterns/ask failed: ${response.status}`);
  }
  return (await response.json()) as PatternProposal;
}

export async function savePattern(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: { pattern_id: string | null; name: string; definition: PatternQuery },
): Promise<SavedPattern> {
  // ADR-099 Amendment 3: a saved pattern is the dataset's, saved and found within the case.
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/patterns/save`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw await failure(response, `POST .../patterns/save failed: ${response.status}`);
  }
  return (await response.json()) as SavedPattern;
}

export async function listPatterns(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<SavedPattern[]> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/patterns`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) {
    throw new Error(`GET .../patterns failed: ${response.status}`);
  }
  const body = (await response.json()) as { patterns: SavedPattern[] };
  return body.patterns;
}

export async function loadPattern(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  patternId: string,
): Promise<SavedPattern> {
  const response = await fetch(
    `${caseUrl(apiBaseUrl, investigationId)}/patterns/${encodeURIComponent(patternId)}`,
    {
      headers: { Authorization: `Bearer ${bearerToken}` },
    },
  );
  if (!response.ok) {
    throw new Error(`GET .../patterns/${patternId} failed: ${response.status}`);
  }
  return (await response.json()) as SavedPattern;
}
