// The Glass's side of ADR-052 (owner, 29 September 2026: "I don't yet see any option for selecting
// the dataset / case that I want to work on"). This lists the cases an account holds a level on
// and creates a named one. It enforces nothing: the Conduit does (ADR-050), and answers a case the
// account may not see with the same "not found" as one that does not exist.
import { utcStamp } from "../time/utcStamp";
import { rememberCaseView } from "../views/lensHandoff";
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
  /** ADR-099 Amendment 12: a source, or a composite read as its members. An analyst layer is never
   * sent to the Glass (ADR-143 decision 1). Older Conduits send neither field. */
  kind?: "source" | "composite";
  members?: string[];
}

/** What a new case reads (ADR-099 Amendment 12 item 6): one existing dataset, or a new one named
 * here. There is no third choice: the Conduit no longer gives a case a dataset of its own. */
export type CaseData = { datasetId: string } | { newDatasetName: string };

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

/** Changes what a case reads: its Author's. Exactly one dataset, a source or a composite (ADR-099
 * Amendment 12); the Conduit refuses two, none, and any dataset not of the Author's unit, with one
 * answer. */
export async function setCaseDatasets(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  datasetIds: string[],
): Promise<Dataset[]> {
  if (datasetIds.length !== 1) throw new Error("A case reads exactly one dataset.");
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/datasets`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_ids: datasetIds }),
    },
  );
  if (response.status === 403) throw new Error("Only the case's Author can change what it reads.");
  if (response.status === 422) throw new Error("That dataset is not one this case can read.");
  if (response.status === 409) throw new Error(await refusalWords(response, "This case's dataset cannot be changed"));
  if (!response.ok) throw new Error(`Could not change what this case reads (${response.status}).`);
  return (await response.json()) as Dataset[];
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
  data: CaseData,
  domains: readonly DomainPack[] = [],
): Promise<{ id: string; name: string; domains?: DomainPack[] }> {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error("A case needs a name.");
  }
  const reads =
    "datasetId" in data
      ? { dataset_ids: [data.datasetId] }
      : { new_dataset_name: data.newDatasetName.trim() || trimmed };
  const response = await fetch(`${apiBaseUrl}/v1/investigations`, {
    method: "POST",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    // ADR-126: the packs shown, `[]` when none is ticked, so the case counts as chosen (POLE).
    body: JSON.stringify({ name: trimmed, ...reads, domains: sortedDomains(domains) }),
  });
  if (response.status === 422) {
    throw new Error(
      "datasetId" in data
        ? "That dataset is not one this case can read."
        : "Your unit already has a dataset of that name; choose another name.",
    );
  }
  if (!response.ok) {
    throw new Error(`Could not create the case (${response.status}).`);
  }
  return (await response.json()) as { id: string; name: string; domains?: DomainPack[] };
}

/** A refusal in the Conduit's own words (L3.H1: a dataset's home case is kept, `home_case_kept`),
 * after `lead`: "This case cannot be removed: this is its dataset's home case, …". */
async function refusalWords(response: Response, lead: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: { message?: string } };
    const said = body.detail?.message;
    if (typeof said === "string" && said) return `${lead}: ${said}.`;
  } catch {
    /* no words sent: the lead alone */
  }
  return `${lead}.`;
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
  if (response.status === 409) {
    throw new Error(await refusalWords(response, "This case cannot be removed"));
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
export function caseUrl(id: string, view?: "ingest" | "questions", caseView?: string): string {
  // `from=case` makes the Glass sign back in by itself: the reload drops the in-memory sign-in
  // (`auth/launcherHandoff.ts`), and without it the person met the sign-in screen after every switch.
  const base = `/?investigation=${encodeURIComponent(id)}&from=case`;
  const withView = view ? `${base}&view=${view}` : base;
  // ADR-144: a case opened on one of its views (`case_view`), shown as a lens on it.
  return caseView ? `${withView}&case_view=${encodeURIComponent(caseView)}` : withView;
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

/** Opens a case on one of its views (ADR-144): the case is loaded as any switch loads it, and the
 * view is then opened over it as a lens. */
export function openCaseView(
  caseId: string,
  viewId: string,
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, caseId);
  rememberCaseView(caseId, viewId);
  navigate(caseUrl(caseId, undefined, viewId));
}

/** How a dataset is offered in a choice: its name, and for a composite how many it joins. */
export function datasetChoiceLabel(dataset: Dataset): string {
  const joins = dataset.kind === "composite" ? (dataset.members?.length ?? 0) : 0;
  return joins > 0 ? `${dataset.name} (a composite of ${joins} datasets)` : dataset.name;
}

/** A dataset as the Glass names it: its name and its id, so two that read alike are told apart
 * (ADR-099 Amendment 6). An id of twelve characters or fewer (the seeds' `enron`) is shown whole;
 * a longer one (a ULID) by its last five. */
export function datasetLabel(id: string, name: string): string {
  return `${name} · ${id.length <= 12 ? id : `\u2026${id.slice(-5)}`}`;
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
