// The one place the trend and pack calls are made (ADR-113): a bearer-authenticated JSON request
// against a case, and the refusals said in words — never a bare status code.
import type { ReportsApi } from "./api";

export interface Reply {
  status: number;
  ok: boolean;
  body: unknown;
}

export function caseUrl(api: ReportsApi, path: string): string {
  return `${api.apiBaseUrl}/v1/investigations/${encodeURIComponent(api.investigationId)}/${path}`;
}

export async function send(api: ReportsApi, method: string, path: string, body?: unknown): Promise<Reply> {
  const response = await fetch(caseUrl(api, path), {
    method,
    headers: {
      Authorization: `Bearer ${api.bearerToken}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const parsed: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  return { status: response.status, ok: response.ok, body: parsed };
}

export function fieldOf(body: unknown, name: string): unknown {
  return body && typeof body === "object" ? (body as Record<string, unknown>)[name] : undefined;
}

/** A refusal with no special body, in words. `what` completes "could not …". */
export function refusal(reply: Reply, what: string): Error {
  const detail = fieldOf(reply.body, "detail");
  if (typeof detail === "string" && detail.length > 0) return new Error(detail);
  if (reply.status === 403) return new Error(`You do not have the right to ${what} in this case.`);
  if (reply.status === 404) return new Error("That could not be found. It may have been removed; reload to see what is there now.");
  return new Error(`Could not ${what} (the server answered ${reply.status}). Try again, and tell an administrator if it keeps happening.`);
}
