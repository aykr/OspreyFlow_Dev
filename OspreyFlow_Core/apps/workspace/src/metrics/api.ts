// Fetch wrapper for `POST /v1/investigations/{id}/compute/{metric}`
// (`services/api/compute_routes.py`) — mirrors `analytics/api.ts`'s own conventions. `services/
// api/compute_routes.py`'s `ComputeMetricRequest`/`ComputeMetricAccepted` are route-level models,
// not `packages/schemas/`-generated ones (the same "hand-typed inline" shape
// `resolution/ThresholdControl.tsx`'s own `{ threshold: number }` already establishes for
// `resolution.py`'s own route models) — no generated type exists for either, so both are declared
// here by hand instead.
export type ComputeMetricName =
  | "degree"
  | "weighted_degree"
  | "betweenness"
  | "eigenvector"
  | "pagerank"
  | "clustering_coefficient"
  | "communities"
  | "clique_metric";

export interface ComputeMetricAccepted {
  mode: "sync" | "job";
  values?: Record<string, number>;
  communities?: Record<string, string>;
  job_id?: string;
}

export async function fetchComputeMetric(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  metric: ComputeMetricName,
  options: { kMin?: number; kMax?: number } = {},
): Promise<ComputeMetricAccepted> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/compute/${metric}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ k_min: options.kMin ?? 4, k_max: options.kMax ?? 30 }),
    },
  );
  if (!response.ok) {
    throw new Error(`POST .../compute/${metric} failed: ${response.status}`);
  }
  return (await response.json()) as ComputeMetricAccepted;
}
