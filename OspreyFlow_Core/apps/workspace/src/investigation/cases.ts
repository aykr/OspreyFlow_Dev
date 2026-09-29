// The Glass's side of ADR-052 (owner, 29 September 2026: "I don't yet see any option for selecting
// the dataset / case that I want to work on"). This lists the cases an account holds a level on
// and creates a named one. It enforces nothing: the Conduit does (ADR-050), and answers a case the
// account may not see with the same "not found" as one that does not exist.
import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";

export type AccessLevel = "viewer" | "editor" | "author";

export interface CaseListing {
  id: string;
  name: string;
  level: AccessLevel;
  created_at: string;
  created_by: string;
  branched_from?: string | null;
}

export async function listCases(apiBaseUrl: string, bearerToken: string): Promise<CaseListing[]> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) {
    throw new Error(`Could not load your cases (${response.status}).`);
  }
  return (await response.json()) as CaseListing[];
}

export async function createCase(
  apiBaseUrl: string,
  bearerToken: string,
  name: string,
): Promise<{ id: string; name: string }> {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error("A case needs a name.");
  }
  const response = await fetch(`${apiBaseUrl}/v1/investigations`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: trimmed }),
  });
  if (!response.ok) {
    throw new Error(`Could not create the case (${response.status}).`);
  }
  return (await response.json()) as { id: string; name: string };
}

/** The URL the Glass already reads on load (`initialInvestigationId`). */
export function caseUrl(id: string): string {
  return `/?investigation=${encodeURIComponent(id)}`;
}

/** Switching case reloads the page on purpose: the working set, the cross-filter store and the
 * delta stream are each built once per case, so a full navigation is the one way to be sure none
 * of the previous case's state is left behind. */
export function openCase(
  id: string,
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, id);
  navigate(caseUrl(id));
}
