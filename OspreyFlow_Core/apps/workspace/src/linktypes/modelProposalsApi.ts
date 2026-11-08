// The Studio's *1 Model* tab's calls for the link types analysts proposed (ADR-143 decision 9, ADR-090
// Amendment 4; L3.5), kept apart from `linkTypesApi.ts` because their screen is the Ingest Studio's,
// not the Glass's or Admin's (`test_place_routes.py`'s `MOVED`).
import { LinkTypeError, send } from "./http";
import type { ProposalStatus } from "./linkTypesApi";

/** A proposal as the Model tab is told of it: never the case it was made in (rule 3). */
export interface ModelProposal {
  id: string;
  name: string;
  label?: string | null;
  from_types: string[];
  to_types: string[];
  directed: boolean;
  proposed_by: string;
  proposed_at: string;
  reason: string;
  status: ProposalStatus;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  basis?: "direct" | "probabilistic" | null;
  /** Where its type stands in the dataset's model: live, in the draft, or neither. */
  in_model?: "live" | "draft" | null;
}

const modelUrl = (base: string, datasetId: string) =>
  `${base}/v1/datasets/${encodeURIComponent(datasetId)}/model/proposals`;

export async function listModelProposals(
  apiBaseUrl: string,
  bearerToken: string,
  datasetId: string,
): Promise<ModelProposal[]> {
  const body = await send<{ proposals?: ModelProposal[] } | null>(modelUrl(apiBaseUrl, datasetId), bearerToken);
  if (!body || !Array.isArray(body.proposals)) {
    throw new LinkTypeError("failed", "The server's answer was not a list of proposals.");
  }
  return body.proposals;
}

export function decideModelProposal(
  apiBaseUrl: string,
  bearerToken: string,
  datasetId: string,
  proposalId: string,
  decision: "accept" | "decline",
  reason: string,
  basis?: "direct" | "probabilistic",
): Promise<ModelProposal> {
  return send(
    `${modelUrl(apiBaseUrl, datasetId)}/${encodeURIComponent(proposalId)}/${decision}`,
    bearerToken,
    decision === "accept" ? { basis, reason } : { reason },
  );
}
