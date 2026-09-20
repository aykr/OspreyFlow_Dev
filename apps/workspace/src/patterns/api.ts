// Fetch wrappers for `POST /v1/patterns/preview` and `POST /v1/patterns/run`
// (`services/api/patterns.py`) — mirrors `metrics/api.ts`'s own conventions. Not investigation
// -scoped, the same reasoning `search.py`/`GlobalSearch.tsx` already give for `POST /v1/search`.
import type { PatternQuery, Subgraph } from "../../../../packages/schemas/generated";

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

export async function fetchPatternPreview(
  apiBaseUrl: string,
  bearerToken: string,
  pattern: PatternQuery,
): Promise<PatternPreview> {
  const response = await fetch(`${apiBaseUrl}/v1/patterns/preview`, {
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
  pattern: PatternQuery,
): Promise<PatternRunAccepted> {
  const response = await fetch(`${apiBaseUrl}/v1/patterns/run`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(pattern),
  });
  if (!response.ok) {
    throw new Error(`POST /v1/patterns/run failed: ${response.status}`);
  }
  return (await response.json()) as PatternRunAccepted;
}
