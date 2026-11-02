// The Conduit's connection-strength routes (ADR-139; `services/api/app.py`, "connection strength"):
// the case's legend and override, each working-set link's strength, shared-attribute rarity, and the
// installation-wide influencers' maker–checker. Each refusal is said in the Conduit's own words where
// it gave them, never as a bare status.
import type {
  CaseInfluencers,
  CaseInfluencersInput,
  ConnectionStrengths,
  InfluencerSetHistory,
  InfluencerSetVersion,
  RarityResult,
  StrengthInfluencer,
} from "../../../../packages/schemas/generated";

export type RarityScope = "dataset" | "case";

async function call<T>(url: string, bearerToken: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearerToken}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    let said: string | null = null;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const detail = (body.detail ?? body) as Record<string, unknown>;
      said = (detail.message ?? detail.reason ?? null) as string | null;
      if (detail.error === "limit_exceeded") {
        said = "There are too many pairs in this view to work out rarity; narrow the view or branch it first.";
      }
      if (detail.error === "own_change") said = (detail.message as string) ?? "You proposed this; a second person must approve it.";
    } catch {
      // No words in the body: the status says it.
    }
    throw new Error(said ?? `The request was refused (${response.status}).`);
  }
  return (await response.json()) as T;
}

function caseUrl(apiBaseUrl: string, investigationId: string, path: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/${path}`;
}

export function fetchCaseInfluencers(apiBaseUrl: string, bearerToken: string, investigationId: string) {
  return call<CaseInfluencers>(caseUrl(apiBaseUrl, investigationId, "strength-influencers"), bearerToken);
}

export function saveCaseInfluencers(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  body: CaseInfluencersInput,
) {
  return call<CaseInfluencers>(caseUrl(apiBaseUrl, investigationId, "strength-influencers"), bearerToken, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function fetchConnectionStrengths(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  edgeIds: string[] | null = null,
) {
  return call<ConnectionStrengths>(caseUrl(apiBaseUrl, investigationId, "connection-strength"), bearerToken, {
    method: "POST",
    body: JSON.stringify({ edge_ids: edgeIds }),
  });
}

export function fetchRarity(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  scope: RarityScope,
  pairs: [string, string][] = [],
) {
  return call<RarityResult>(caseUrl(apiBaseUrl, investigationId, "rarity"), bearerToken, {
    method: "POST",
    body: JSON.stringify({ scope, pairs }),
  });
}

export function fetchInfluencerHistory(apiBaseUrl: string, bearerToken: string) {
  return call<InfluencerSetHistory>(`${apiBaseUrl}/v1/strength-influencers`, bearerToken);
}

export function proposeInfluencers(
  apiBaseUrl: string,
  bearerToken: string,
  influencers: StrengthInfluencer[],
  words: string,
) {
  return call<InfluencerSetVersion>(`${apiBaseUrl}/v1/strength-influencers`, bearerToken, {
    method: "POST",
    body: JSON.stringify({ influencers, words }),
  });
}

export function approveInfluencers(apiBaseUrl: string, bearerToken: string, version: number) {
  return call<InfluencerSetVersion>(`${apiBaseUrl}/v1/strength-influencers/${version}/approve`, bearerToken, {
    method: "POST",
  });
}

export function sendBackInfluencers(apiBaseUrl: string, bearerToken: string, version: number, words: string) {
  return call<InfluencerSetVersion>(`${apiBaseUrl}/v1/strength-influencers/${version}/send-back`, bearerToken, {
    method: "POST",
    body: JSON.stringify({ words }),
  });
}
