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
    throw new Error(`POST /v1/patterns/preview failed: ${response.status}`);
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
    throw new Error(`POST /v1/patterns/run failed: ${response.status}`);
  }
  return (await response.json()) as PatternRunAccepted;
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
    throw new Error(`POST .../patterns/save failed: ${response.status}`);
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
