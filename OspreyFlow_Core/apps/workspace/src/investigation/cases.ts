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
  /** This account has closed the case's tab (ADR-084). Says nothing about anyone else's view. */
  tab_hidden?: boolean;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Written by hand, not by Intl: the month abbreviation differs between engines ("Sep" or "Sept").
function utcStamp(made: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  return (
    `${made.getUTCDate()} ${MONTHS[made.getUTCMonth()]} ${made.getUTCFullYear()} ` +
    `${two(made.getUTCHours())}:${two(made.getUTCMinutes())} UTC`
  );
}

/** What a case is called on screen. A case made before names existed has none; it is shown as
 * untitled with when it was made, never as an empty button. */
export function caseLabel(entry: Pick<CaseListing, "name" | "created_at">): string {
  const name = entry.name.trim();
  if (name) return name;
  const made = new Date(entry.created_at);
  if (Number.isNaN(made.getTime())) return "Untitled case";
  return `Untitled case · created ${utcStamp(made)}`;
}

/** Named cases first, then untitled ones; newest first within each. */
export function orderCases(cases: readonly CaseListing[]): CaseListing[] {
  return [...cases].sort((a, b) => {
    const named = Number(Boolean(b.name.trim())) - Number(Boolean(a.name.trim()));
    if (named !== 0) return named;
    return b.created_at.localeCompare(a.created_at);
  });
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

/** A soft remove: the case leaves every list and answers "not found", and nothing is deleted from
 * the database or the graph (ADR-052 Amendment 7). An Author may; so may an administrator of the
 * case's own unit. The Conduit decides; this only asks. */
export async function removeCase(
  apiBaseUrl: string,
  bearerToken: string,
  id: string,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (response.status === 403) {
    throw new Error("You do not have permission to remove this case.");
  }
  if (response.status === 404) {
    throw new Error("That case was not found. It may already have been removed.");
  }
  if (!response.ok) {
    throw new Error(`The case could not be removed (${response.status}).`);
  }
  try {
    if (sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY) === id) {
      sessionStorage.removeItem(INVESTIGATION_ID_SESSION_KEY);
    }
  } catch {
    /* a convenience about this tab: never worth failing a removal over */
  }
}

/** The URL the Glass already reads on load (`initialInvestigationId`). */
export function caseUrl(id: string, view?: "ingest"): string {
  // `from=case` makes the Glass sign back in by itself: the reload drops the in-memory sign-in
  // (`auth/launcherHandoff.ts`), and without it the person met the sign-in screen after every switch.
  const base = `/?investigation=${encodeURIComponent(id)}&from=case`;
  return view ? `${base}&view=${view}` : base;
}

/** Switching case reloads the page on purpose: the working set, the cross-filter store and the
 * delta stream are each built once per case, so a full navigation is the one way to be sure none
 * of the previous case's state is left behind. */
export function openCase(
  id: string,
  view?: "ingest",
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, id);
  navigate(caseUrl(id, view));
}

/** A case and the branches made from it, for the strip of tabs (ADR-084). A branch of a branch
 * belongs to the original case's family too, so every tab leads back to the same place. The root is
 * the topmost case this account can see: if the original was removed or never shared, the oldest
 * ancestor that is listed stands in for it. */
export interface BranchFamily {
  root: CaseListing;
  branches: CaseListing[];
}

function rootOf(byId: Map<string, CaseListing>, start: CaseListing): CaseListing {
  let top = start;
  const seen = new Set<string>([start.id]);
  for (;;) {
    const parent = top.branched_from ? byId.get(top.branched_from) : undefined;
    if (!parent || seen.has(parent.id)) return top;
    seen.add(parent.id);
    top = parent;
  }
}

export function branchFamily(cases: readonly CaseListing[], currentId: string): BranchFamily | null {
  const byId = new Map(cases.map((entry) => [entry.id, entry]));
  const current = byId.get(currentId);
  if (!current) return null;
  const root = rootOf(byId, current);
  const branches = cases
    .filter((entry) => entry.id !== root.id && rootOf(byId, entry).id === root.id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  return { root, branches };
}

/** The branches shown as tabs: those this account has not closed, and always the one on screen. */
export function openTabs(family: BranchFamily, currentId: string): CaseListing[] {
  return family.branches.filter((entry) => !entry.tab_hidden || entry.id === currentId);
}

/** Closes (`hidden`) or reopens a case's tab for this account only. */
export async function setTabHidden(
  apiBaseUrl: string,
  bearerToken: string,
  id: string,
  hidden: boolean,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(id)}/tab`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ hidden }),
  });
  if (response.status === 404) {
    throw new Error("That case was not found. It may have been removed.");
  }
  if (!response.ok) {
    throw new Error(`The tab could not be ${hidden ? "closed" : "shown"} (${response.status}).`);
  }
}
