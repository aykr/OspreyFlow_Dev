// The Glass's side of ADR-052 (owner, 29 September 2026: "I don't yet see any option for selecting
// the dataset / case that I want to work on"). This lists the cases an account holds a level on
// and creates a named one. It enforces nothing: the Conduit does (ADR-050), and answers a case the
// account may not see with the same "not found" as one that does not exist.
import { MONTHS, utcStamp } from "../time/utcStamp";
import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";

export type AccessLevel = "viewer" | "editor" | "author";

/** ADR-126: a domain pack a case can carry. Written by hand, since these types sit outside
 * `schemas-check`; the Conduit's `DomainPack` (`packages/schemas/domain.py`) is the one definition,
 * and an empty list is the POLE core model alone. */
export type DomainPack = "fibo" | "niem" | "stix";

/** The packs a case can carry, in the catalogue's order, with the Studio's labels (the Conduit's
 * `pack_catalogue`; `test_case_seed_packs.py` holds the two in step). Written by hand, as above. */
export const DOMAIN_PACKS: readonly { name: DomainPack; label: string }[] = [
  { name: "fibo", label: "Financial fraud and AML (FIBO)" },
  { name: "niem", label: "Crime case analysis (NIEM)" },
  { name: "stix", label: "Cyber threat analytics (STIX 2.1)" },
];

/** What an empty list of packs is called: the core model alone. */
export const POLE_LABEL = "Bespoke POLE (the core model)";

/** The packs in the catalogue's order, once each: what is sent and what is shown. */
export function sortedDomains(domains: readonly DomainPack[]): DomainPack[] {
  return DOMAIN_PACKS.map((p) => p.name).filter((name) => domains.includes(name));
}

/** The packs named by label, or the POLE core model when there are none. */
export function domainLabels(domains: readonly DomainPack[]): string {
  const held = DOMAIN_PACKS.filter((p) => domains.includes(p.name));
  return held.length > 0 ? held.map((p) => p.label).join(", ") : POLE_LABEL;
}

export interface CaseListing {
  id: string;
  name: string;
  level: AccessLevel;
  created_at: string;
  created_by: string;
  branched_from?: string | null;
  /** ADR-126: the case's domain packs, sorted; empty is the POLE core model. Every reader of the
   * case may see it: it says what kind of case it is, never what it holds. */
  domains?: DomainPack[];
  /** This account has closed the case's tab (ADR-084). Says nothing about anyone else's view. */
  tab_hidden?: boolean;
  /** ADR-099: the names of the datasets the case reads, in order. */
  datasets?: string[];
  /** Their ids, in the same order, so a name is shown with its id (ADR-099 Amendment 6). */
  dataset_ids?: string[];
}

/** A body of data held by the unit (ADR-099): the Enron corpus, Fixture Corp, a Studio load's. */
export interface Dataset {
  id: string;
  name: string;
  owning_unit: string;
}

/** The datasets of the caller's unit, for a new case to name. */
export async function listDatasets(apiBaseUrl: string, bearerToken: string): Promise<Dataset[]> {
  const response = await fetch(`${apiBaseUrl}/v1/datasets`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw new Error(`Could not load the datasets (${response.status}).`);
  return (await response.json()) as Dataset[];
}

/** The datasets a case reads, in order. */
export async function caseDatasets(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Dataset[]> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/datasets`,
    { headers: { Authorization: `Bearer ${bearerToken}` } },
  );
  if (!response.ok) throw new Error(`Could not load what this case reads (${response.status}).`);
  return (await response.json()) as Dataset[];
}

/** Changes what a case reads: its Author's. The Conduit refuses none, and any dataset not of the
 * Author's unit, with one answer. */
export async function setCaseDatasets(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  datasetIds: string[],
): Promise<Dataset[]> {
  if (datasetIds.length === 0) throw new Error("A case reads at least one dataset.");
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/datasets`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_ids: datasetIds }),
    },
  );
  if (response.status === 403) throw new Error("Only the case's Author can change what it reads.");
  if (response.status === 422) throw new Error("One of those datasets is not one this case can read.");
  if (!response.ok) throw new Error(`Could not change what this case reads (${response.status}).`);
  return (await response.json()) as Dataset[];
}

/** An Author's change of the case's domain models (ADR-126): `PATCH /v1/investigations/{id}` with
 * the packs alone. The Conduit refuses anyone else (403); the answer is the case as it now stands. */
export async function changeCaseDomains(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  domains: readonly DomainPack[],
): Promise<DomainPack[]> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ domains: sortedDomains(domains) }),
  });
  if (response.status === 403) throw new Error("Only the case's Author can change its domain models.");
  if (response.status === 404) throw new Error("That case was not found.");
  if (!response.ok) throw new Error(`Could not change the domain models (${response.status}).`);
  const saved = (await response.json()) as { domains?: DomainPack[] };
  return saved.domains ?? [];
}

/** What a case is called on screen. A case made before names existed has none; it is shown as
 * untitled with when it was made, never as an empty button. */
/** ADR-115 Amendment 1 point 5 (the owner's ruling of 13 October 2026): a case's scope is the
 * datasets it reads (ADR-099), shown as a mono badge beside its name — the first by name, then how
 * many more — with all of them named in its title. Unknown datasets: no badge. */
export function scopeBadge(datasets: readonly string[] | undefined): { text: string; title: string } | null {
  if (datasets === undefined) return null;
  if (datasets.length === 0) return { text: "NO DATA", title: "This case reads no dataset" };
  const [first, ...rest] = datasets;
  const named = rest.length === 0 ? first! : `${datasets.slice(0, -1).join(", ")} and ${datasets.at(-1)}`;
  return {
    text: rest.length === 0 ? first!.toUpperCase() : `${first!.toUpperCase()} +${rest.length}`,
    title: `This case reads ${named}`,
  };
}

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

/** Whether this account can open case `id`: false only when the Conduit refuses it (403/404), so a
 * case left in the tab by another account is dropped and the picker shows (9 October 2026). A
 * failing or unreachable server keeps the case: it is not a refusal. */
export async function caseIsOpenable(apiBaseUrl: string, bearerToken: string, id: string): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(id)}`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    });
    return response.status !== 403 && response.status !== 404;
  } catch {
    return true;
  }
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
  datasetIds: string[] = [],
  domains: readonly DomainPack[] = [],
): Promise<{ id: string; name: string; domains?: DomainPack[] }> {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error("A case needs a name.");
  }
  // ADR-099: with none named, the Conduit gives the case a dataset of its own.
  const response = await fetch(`${apiBaseUrl}/v1/investigations`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    // ADR-126: the packs shown, `[]` when none is ticked, so the case counts as chosen (POLE).
    body: JSON.stringify({
      name: trimmed,
      ...(datasetIds.length > 0 ? { dataset_ids: datasetIds } : {}),
      domains: sortedDomains(domains),
    }),
  });
  if (response.status === 422) {
    throw new Error("One of those datasets is not one this case can read.");
  }
  if (!response.ok) {
    throw new Error(`Could not create the case (${response.status}).`);
  }
  return (await response.json()) as { id: string; name: string; domains?: DomainPack[] };
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
export function caseUrl(id: string, view?: "ingest" | "questions"): string {
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
  view?: "ingest" | "questions",
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, id);
  navigate(caseUrl(id, view));
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

/** The picker's rows (ADR-084 Amendment 3): each original case in `orderCases`' order, followed by
 * every branch in its family (as `branchFamily` groups them) oldest first, marked as a branch. A
 * branch whose original this account cannot see sits under its oldest visible ancestor, which then
 * heads the family. No case is left out. */
export function nestCases(
  cases: readonly CaseListing[],
): Array<{ entry: CaseListing; branch: boolean }> {
  const byId = new Map(cases.map((entry) => [entry.id, entry]));
  const families = new Map<string, CaseListing[]>();
  for (const entry of cases) {
    const root = rootOf(byId, entry);
    if (root.id !== entry.id) families.set(root.id, [...(families.get(root.id) ?? []), entry]);
  }
  const roots = orderCases(cases.filter((entry) => rootOf(byId, entry).id === entry.id));
  return roots.flatMap((root) => [
    { entry: root, branch: false },
    ...(families.get(root.id) ?? [])
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
      .map((entry) => ({ entry, branch: true })),
  ]);
}


/** A dataset as the Glass names it: its name and its id, so two that read alike are told apart
 * (ADR-099 Amendment 6). An id of twelve characters or fewer (the seeds' `enron`) is shown whole;
 * a longer one (a ULID) by its last five. */
export function datasetLabel(id: string, name: string): string {
  return `${name} · ${id.length <= 12 ? id : `\u2026${id.slice(-5)}`}`;
}

// --- A branch in its case's tree (ADR-084 Amendment 4) ------------------------------------------
// The owner, 14 October 2026: "the current display method for the Branch and main case is very
// confusing, i need a method to delete a branch as through the Glass view". A branch is shown beneath
// its case, named for what it holds and when it was made rather than by repeating the case's name.

const BRANCH_DEFAULT = /^Branch of .+ \((\d+) (?:node|nodes)\)$/;

function shortStamp(made: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  return `${made.getUTCDate()} ${MONTHS[made.getUTCMonth()]} ${two(made.getUTCHours())}:${two(made.getUTCMinutes())}`;
}

/** A branch's own name: as renamed by someone, or, while it keeps the name branching gave it, how
 * many nodes it was made from and when (UTC). */
export function branchLabel(entry: Pick<CaseListing, "name" | "created_at">): string {
  const name = entry.name.trim();
  const made = new Date(entry.created_at);
  const when = Number.isNaN(made.getTime()) ? "" : ` · ${shortStamp(made)}`;
  const sized = BRANCH_DEFAULT.exec(name);
  if (sized) {
    const count = Number(sized[1]);
    return `${count} ${count === 1 ? "node" : "nodes"}${when}`;
  }
  if (!name || name.startsWith("Branch of ")) return `Branch${when}`;
  return name;
}

/** The case a branch came from, when this account can see it: where deleting the branch you are in
 * takes you. `null` for an original case, or a branch whose original is not listed. */
export function returnFor(cases: readonly CaseListing[], id: string): CaseListing | null {
  const entry = cases.find((c) => c.id === id);
  if (!entry?.branched_from) return null;
  return cases.find((c) => c.id === entry.branched_from) ?? null;
}

/** Renames a case (its Author only: the Conduit decides). */
export async function renameCase(apiBaseUrl: string, bearerToken: string, id: string, name: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: name.trim() }),
  });
  if (response.status === 403) throw new Error("Only the case's Author can rename it.");
  if (response.status === 404) throw new Error("That case was not found. It may have been removed.");
  if (response.status === 422) throw new Error("A case needs a name.");
  if (!response.ok) throw new Error(`The case could not be renamed (${response.status}).`);
}
