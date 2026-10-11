// Who can open a case (ADR-052 §7, Amendment 4): the Glass's side of `…/access`. Everyone reads
// their own level; only an Author is served the grants (and, ADR-106, the grantees' names). The
// Conduit decides every change; this only asks and says the refusal in words.
import type { AccessLevel } from "./cases";

export interface CaseAccess {
  your_level: AccessLevel | null;
  unit_level: AccessLevel | null;
  /** Account id → level; null unless the caller is the case's Author. */
  grants: Record<string, AccessLevel> | null;
  /** Display names for the ids in `grants`; an id with no name is absent. */
  names?: Record<string, string> | null;
}

const base = (apiBaseUrl: string, id: string) =>
  `${apiBaseUrl}/v1/investigations/${encodeURIComponent(id)}/access`;

/** Null when the account does not hold the right to share cases (ADR-112 `share_case`): the panel
 * is then not shown, rather than shown as a failure. */
export async function caseAccess(apiBaseUrl: string, bearerToken: string, id: string): Promise<CaseAccess | null> {
  const response = await fetch(base(apiBaseUrl, id), { headers: { Authorization: `Bearer ${bearerToken}` } });
  if (response.status === 403) return null;
  if (!response.ok) throw new Error(`Could not read who can open this case (${response.status}).`);
  return (await response.json()) as CaseAccess;
}

function refusal(status: number, doing: string): Error {
  if (status === 403) return new Error("Only the case's Author can change who can open it.");
  if (status === 404) return new Error("That case was not found. It may have been removed.");
  if (status === 422) return new Error("An account id is 1 to 200 characters.");
  return new Error(`Could not ${doing} (${status}).`);
}

export async function grantCaseAccess(
  apiBaseUrl: string,
  bearerToken: string,
  id: string,
  accountId: string,
  level: AccessLevel,
): Promise<void> {
  const account = accountId.trim();
  if (!account) throw new Error("Name the account to give access to.");
  const response = await fetch(`${base(apiBaseUrl, id)}/grants/${encodeURIComponent(account)}`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ level }),
  });
  if (!response.ok) throw refusal(response.status, "give access");
}

export async function removeCaseAccess(
  apiBaseUrl: string,
  bearerToken: string,
  id: string,
  accountId: string,
): Promise<void> {
  const response = await fetch(`${base(apiBaseUrl, id)}/grants/${encodeURIComponent(accountId)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw refusal(response.status, "remove access");
}

export const LEVEL_NAMES: Record<AccessLevel, string> = {
  viewer: "Viewer",
  editor: "Editor",
  author: "Author",
};
