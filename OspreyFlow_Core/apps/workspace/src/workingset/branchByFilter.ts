import type { LimitExceeded } from "./models";

export interface BranchByFilterRequest {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** Entity types, from the ontology the Glass holds. Absent: no narrowing by type. */
  entityTypes?: string[];
  /** A date window, as `YYYY-MM-DD` from a date field. Either end may be left out. */
  validFrom?: string;
  validTo?: string;
  name?: string;
}

export type BranchByFilterResult =
  | { ok: true; id: string; name: string }
  | { ok: false; kind: "limit_exceeded"; wouldBe: LimitExceeded }
  | { ok: false; kind: "nothing_matched" }
  | { ok: false; kind: "nothing_chosen" }
  | { ok: false; kind: "failed"; message: string };

/**
 * Builds a new case from the reader's own view, narrowed to entity types, a date window, or both
 * (`POST /v1/investigations/{id}/branch-by-filter`, ADR-124 decision 2), for a reader whose view is
 * past the cap. Each outcome is a value: a case made; a choice still past the cap, with the
 * filtered figure (`limit_exceeded`, 409); a choice nothing matched (`nothing_to_branch`, 422, the
 * same answer for a type only hidden material holds as for one that does not exist, so the Glass
 * says only that nothing matched); or a failure. A request that chooses nothing is refused here,
 * before the server is asked.
 */
export async function branchByFilter(
  fetcher: typeof fetch,
  req: BranchByFilterRequest,
): Promise<BranchByFilterResult> {
  if (req.entityTypes === undefined && !req.validFrom && !req.validTo) {
    return { ok: false, kind: "nothing_chosen" };
  }
  const body: Record<string, unknown> = {};
  if (req.entityTypes !== undefined) body.entity_types = req.entityTypes;
  if (req.validFrom) body.valid_from = `${req.validFrom}T00:00:00Z`;
  if (req.validTo) body.valid_to = `${req.validTo}T23:59:59Z`;
  if (req.name) body.name = req.name;
  try {
    const response = await fetcher(
      `${req.apiBaseUrl}/v1/investigations/${req.investigationId}/branch-by-filter`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${req.bearerToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      },
    );
    const answer = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (response.status === 409 && answer.error === "limit_exceeded") {
      return { ok: false, kind: "limit_exceeded", wouldBe: answer as unknown as LimitExceeded };
    }
    if (response.status === 422 && answer.error === "nothing_to_branch") {
      return { ok: false, kind: "nothing_matched" };
    }
    if (!response.ok) {
      return {
        ok: false,
        kind: "failed",
        message: `Branching failed (${response.status}). No case was made. Try again.`,
      };
    }
    if (typeof answer.id !== "string" || answer.id === "") {
      return {
        ok: false,
        kind: "failed",
        message: "Branching got an unexpected reply. No case is confirmed.",
      };
    }
    return { ok: true, id: answer.id, name: typeof answer.name === "string" ? answer.name : "" };
  } catch (err) {
    return {
      ok: false,
      kind: "failed",
      message: `Branching failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
