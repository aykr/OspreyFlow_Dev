// The Ownership place's calls (`06_DECISIONS.md` ADR-109 phase C; `03_CONDUIT_MIDDLEWARE.md`
// §3.8b): find an organisation or account by what it is called, trace who ultimately owns or
// controls it, and put its structure on the canvas. Shapes are the generated ones.
import type { KycStatus, Node, OwnershipView } from "../../../../packages/schemas/generated";
import type { CanvasOutcome } from "../alerts/api";

export interface OwnershipApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

function caseUrl(a: OwnershipApi, path: string): string {
  return `${a.apiBaseUrl}/v1/investigations/${encodeURIComponent(a.investigationId)}/${path}`;
}

async function send<T>(url: string, token: string, what: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { Authorization: `Bearer ${token}`, ...(init.headers ?? {}) } });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (response.ok) return (await response.json()) as T;
  const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: string; would_be?: number; cap?: number };
  if (body.error === "ownership_too_complex" && body.detail) {
    return Promise.reject(new Error(`This structure is not traced: ${body.detail}.`));
  }
  if (body.error === "limit_exceeded") {
    return Promise.reject(new Error(`Too many for the canvas: ${body.would_be ?? "?"} against a limit of ${body.cap ?? "?"}.`));
  }
  if (response.status === 403) return Promise.reject(new Error(`${what} needs Editor access in this case.`));
  if (response.status === 404) return Promise.reject(new Error(`${what}: not found, or not yours to see.`));
  return Promise.reject(new Error(`${what} failed (${response.status}).`));
}

export async function findEntities(a: OwnershipApi, query: string): Promise<Node[]> {
  const body = await send<{ nodes: Node[] }>(caseUrl(a, "suggest"), a.bearerToken, "Finding entities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit: 10, mode: "contains", types: ["Organisation", "Account", "Person"], ignore_case: true }),
  });
  return body.nodes;
}

export const traceOwnership = (a: OwnershipApi, nodeId: string, threshold: number) =>
  send<OwnershipView>(caseUrl(a, `ownership/${encodeURIComponent(nodeId)}?threshold=${threshold}`), a.bearerToken, "Tracing ownership");

export const ownershipToCanvas = (a: OwnershipApi, nodeId: string) =>
  send<CanvasOutcome>(caseUrl(a, `ownership/${encodeURIComponent(nodeId)}/canvas`), a.bearerToken, "Showing the structure", { method: "POST" });

/** ADR-109 phase F: the customer's KYC status and baseline risk, computed now (never stored). */
export const kycStatus = (a: OwnershipApi, nodeId: string) =>
  send<KycStatus>(caseUrl(a, `kyc/${encodeURIComponent(nodeId)}`), a.bearerToken, "Reading the KYC status");
