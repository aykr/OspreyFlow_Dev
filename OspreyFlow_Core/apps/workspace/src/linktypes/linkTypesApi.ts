// Fetch wrappers for the relationship types analysts propose (ADR-090, `services/api/link_types.py`):
// the types a case offers, proposing and withdrawing one there, and the administrator's list and
// decisions. Same conventions as `inspector/linkChangeApi.ts`: Bearer auth, and a refusal thrown
// with the server's own sentence and a `kind` the form words its message from. The shapes are
// written out here because they are not domain models; they mirror the server's.
import type { EdgeTypeDef } from "../../../../packages/schemas/generated";

export type ProposalStatus = "pending" | "promoted" | "rejected" | "withdrawn" | "merged" | "retired";

export interface LinkTypeProposal {
  id: string;
  name: string;
  label?: string | null;
  from_types: string[];
  to_types: string[];
  directed: boolean;
  colour?: string | null;
  thickness?: number | null;
  investigation_id: string;
  owning_unit: string;
  proposed_by: string;
  proposed_at: string;
  reason: string;
  status: ProposalStatus;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  basis?: "direct" | "probabilistic" | null;
  promoted_name?: string | null;
}

export interface ProposeLinkTypeInput {
  name: string;
  label?: string;
  from_types: string[];
  to_types: string[];
  directed: boolean;
  colour?: string;
  thickness?: number;
  reason: string;
}

export interface CaseLinkTypes {
  /** Every type a link in the case may take, the ontology's and the proposed ones. */
  definitions: EdgeTypeDef[];
  /** The names of those proposed and not yet decided, which are marked as proposed. */
  proposed: Set<string>;
}

export type LinkTypeErrorKind = "refused" | "not_found" | "forbidden" | "failed";

export class LinkTypeError extends Error {
  kind: LinkTypeErrorKind;
  constructor(kind: LinkTypeErrorKind, message: string) {
    super(message);
    this.name = "LinkTypeError";
    this.kind = kind;
  }
}

async function refusal(response: Response): Promise<LinkTypeError> {
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // A non-JSON error body falls through to the generic kinds below.
  }
  if (body.error === "proposal_refused") {
    return new LinkTypeError("refused", body.detail ?? "That cannot be done.");
  }
  if (body.error === "proposal_not_found" || response.status === 404) {
    return new LinkTypeError("not_found", "That proposal is no longer there.");
  }
  if (response.status === 403) return new LinkTypeError("forbidden", "forbidden");
  return new LinkTypeError("failed", `request failed: ${response.status}`);
}

async function send<T>(url: string, bearerToken: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new LinkTypeError("failed", "The server could not be reached.");
  }
  if (!response.ok) throw await refusal(response);
  return (await response.json()) as T;
}

const caseUrl = (base: string, id: string) =>
  `${base}/v1/investigations/${encodeURIComponent(id)}/link-types`;

export async function fetchCaseLinkTypes(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<CaseLinkTypes> {
  const body = await send<{ types?: { definition: EdgeTypeDef; proposal_id: string | null }[] } | null>(
    caseUrl(apiBaseUrl, investigationId),
    bearerToken,
  );
  // An answer that is not a list is a failure to load one, not a case with no types.
  if (!body || !Array.isArray(body.types)) {
    throw new LinkTypeError("failed", "The server's answer was not a list of link types.");
  }
  return {
    definitions: body.types.map((t) => t.definition),
    proposed: new Set(body.types.filter((t) => t.proposal_id).map((t) => t.definition.name)),
  };
}

export function proposeLinkType(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  input: ProposeLinkTypeInput,
): Promise<LinkTypeProposal> {
  return send(caseUrl(apiBaseUrl, investigationId), bearerToken, input);
}

export function withdrawProposal(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  proposalId: string,
  reason: string,
): Promise<LinkTypeProposal> {
  return send(
    `${caseUrl(apiBaseUrl, investigationId)}/${encodeURIComponent(proposalId)}/withdraw`,
    bearerToken,
    { reason },
  );
}

export async function listProposals(apiBaseUrl: string, bearerToken: string): Promise<LinkTypeProposal[]> {
  const body = await send<{ proposals?: LinkTypeProposal[] } | null>(
    `${apiBaseUrl}/v1/admin/link-types`,
    bearerToken,
  );
  if (!body || !Array.isArray(body.proposals)) {
    throw new LinkTypeError("failed", "The server's answer was not a list of proposals.");
  }
  return body.proposals;
}

export function promoteProposal(
  apiBaseUrl: string,
  bearerToken: string,
  proposalId: string,
  input: { basis: "direct" | "probabilistic"; reason: string; rename_to?: string },
): Promise<LinkTypeProposal> {
  return send(
    `${apiBaseUrl}/v1/admin/link-types/${encodeURIComponent(proposalId)}/promote`,
    bearerToken,
    input,
  );
}

export function rejectProposal(
  apiBaseUrl: string,
  bearerToken: string,
  proposalId: string,
  reason: string,
): Promise<LinkTypeProposal> {
  return send(
    `${apiBaseUrl}/v1/admin/link-types/${encodeURIComponent(proposalId)}/reject`,
    bearerToken,
    { reason },
  );
}

export function retireLinkType(
  apiBaseUrl: string,
  bearerToken: string,
  name: string,
  reason: string,
): Promise<{ proposals: LinkTypeProposal[] }> {
  return send(`${apiBaseUrl}/v1/admin/link-types/retire`, bearerToken, { name, reason });
}
