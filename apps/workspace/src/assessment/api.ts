// Fetch wrappers for `POST`/`GET /v1/investigations/{id}/judgements`, `.../gaps`,
// `.../assumptions` and `GET /v1/yardstick` (`services/api/app.py`) — mirrors `watches/api.ts`'s
// own conventions (Bearer auth, throw on a non-`ok` response, surface the server's own error body
// where it has one, e.g. `UnverifiableCitationError`'s named `citation_ids`).
//
// **`Yardstick`/`YardstickBand` are hand-mirrored here, not imported from
// `packages/schemas/generated/`** — the same disclosed gap `watches/api.ts`'s own header comment
// already names for `AlertView`/`AlertJumpResult`/`Investigation`: `packages/schemas/
// generate_ts.py`'s own model list is `schemas.{analytics,compute,domain,ingest,model,profile,
// provider_profile}` only, and `Yardstick`/`YardstickBand` live in `packages/ontology/
// yardstick.py`, outside that scope. `Judgement`/`IntelligenceGap`/`Assumption` *are* generated
// (`schemas.domain.ALL_MODELS`) and imported below rather than redeclared.
import type {
  Assumption,
  IntelligenceGap,
  Judgement,
} from "../../../../packages/schemas/generated";

export interface YardstickBand {
  label: string;
  lower: number;
  upper: number;
}

export interface Yardstick {
  name: string;
  bands: YardstickBand[];
}

/** A citation `save` refused, named — the invisible-judgement defect's own fix
 * (`services/api/assessments.py::UnverifiableCitationError`). Thrown by `saveJudgement` instead
 * of a bare `Error` so a caller can name the specific offending citation, not just show a generic
 * "save failed" message (`02_GLASS_FRONTEND.md` §4.1's own copy discipline). */
export class UnverifiableCitationApiError extends Error {
  citationIds: string[];
  constructor(message: string, citationIds: string[]) {
    super(message);
    this.name = "UnverifiableCitationApiError";
    this.citationIds = citationIds;
  }
}

function authHeaders(bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}` };
}

export interface SaveJudgementRequest {
  investigation_id: string;
  statement: string;
  probability_band: string;
  supporting: string[];
  contradicting?: string[];
}

export async function saveJudgement(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: SaveJudgementRequest,
): Promise<Judgement> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/judgements`,
    {
      method: "POST",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!response.ok) {
    let body: { error?: string; detail?: string; citation_ids?: string[] } = {};
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body — fall through to the generic message below.
    }
    if (body.error === "unverifiable_citation" && body.citation_ids) {
      throw new UnverifiableCitationApiError(
        body.detail ?? "citation could not be confirmed as a visible graph node",
        body.citation_ids,
      );
    }
    if (body.error === "no_supporting_reference") {
      throw new Error("a judgement cannot be saved without at least one supporting reference");
    }
    throw new Error(`POST .../judgements failed: ${response.status}`);
  }
  return (await response.json()) as Judgement;
}

export async function listJudgements(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Judgement[]> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/judgements`,
    { headers: authHeaders(bearerToken) },
  );
  if (!response.ok) {
    throw new Error(`GET .../judgements failed: ${response.status}`);
  }
  const body = (await response.json()) as { judgements: Judgement[] };
  return body.judgements;
}

export interface SaveGapRequest {
  investigation_id: string;
  question: string;
  linked_entities?: string[];
  status?: string;
}

export async function saveGap(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: SaveGapRequest,
): Promise<IntelligenceGap> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/gaps`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`POST .../gaps failed: ${response.status}`);
  }
  return (await response.json()) as IntelligenceGap;
}

export async function listGaps(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<IntelligenceGap[]> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/gaps`, {
    headers: authHeaders(bearerToken),
  });
  if (!response.ok) {
    throw new Error(`GET .../gaps failed: ${response.status}`);
  }
  const body = (await response.json()) as { gaps: IntelligenceGap[] };
  return body.gaps;
}

export interface SaveAssumptionRequest {
  investigation_id: string;
  statement: string;
  if_false_impact: string;
  linked_judgements?: string[];
}

export async function saveAssumption(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: SaveAssumptionRequest,
): Promise<Assumption> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/assumptions`,
    {
      method: "POST",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!response.ok) {
    throw new Error(`POST .../assumptions failed: ${response.status}`);
  }
  return (await response.json()) as Assumption;
}

export async function listAssumptions(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Assumption[]> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/assumptions`,
    { headers: authHeaders(bearerToken) },
  );
  if (!response.ok) {
    throw new Error(`GET .../assumptions failed: ${response.status}`);
  }
  const body = (await response.json()) as { assumptions: Assumption[] };
  return body.assumptions;
}

export async function getYardstick(apiBaseUrl: string, bearerToken: string): Promise<Yardstick> {
  const response = await fetch(`${apiBaseUrl}/v1/yardstick`, { headers: authHeaders(bearerToken) });
  if (!response.ok) {
    throw new Error(`GET /v1/yardstick failed: ${response.status}`);
  }
  return (await response.json()) as Yardstick;
}
