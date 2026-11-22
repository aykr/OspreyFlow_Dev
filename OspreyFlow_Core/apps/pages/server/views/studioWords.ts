/**
 * The Studio pages' words and the plain logic they read from (slice IS5a): the frame (`IngestStudio.tsx`, the readiness
 * strip, the rights gate) and Releases (`ReleasesTab.tsx`), re-expressed for the Default tree's pages. Nothing here is a page
 * or a call: a word, or a function from what the Conduit answered to words, so each is a test's to read.
 *
 * Why this is not `packages/glass-shared`: the dataset and pack helpers (`ingest/studio/datasets.ts`, `packs.ts`), the
 * Needs-you words and `releaseName` are shared plain TypeScript, but the server compiles under `NodeNext`, which wants a file
 * extension on every relative import, and the shared package's files have none, so a server file cannot import them (a module
 * the browser build bundles can). The few functions the server needs are written once here and held to the shared ones'
 * answers by `test/server/studioShared.test.ts`, which runs both on the same inputs. When the server is bundled rather than
 * compiled file by file, this file's copies go and the imports come in.
 *
 * Rights are named, never their identifiers; the roles that hold a right are not named at all (see `whyNot`).
 */

export type StudioPlace = "model" | "sources" | "pipelines" | "runs" | "releases";

export type AccessLevel = "viewer" | "editor" | "author";

export interface CaseListing {
  id: string;
  name: string;
  level: AccessLevel;
  created_at: string;
  created_by: string;
  domains?: string[];
  datasets?: string[];
  dataset_ids?: string[];
}

export interface StudioDataset {
  id: string;
  name: string;
}

// ------------------------------------------------------------------------------------------------ the frame's words

export const STUDIO_WORDS = {
  noCase: "Open a case to use the Ingest Studio: it works on the dataset the case loads into.",
  choosePlace: "Choose a place to work in: Model, Sources, Pipelines, Runs or Releases.",
  noDataset: "This case loads into no dataset",
  datasetLabel: "Dataset",
  switchButton: "Switch dataset",
  switchRefused: "None of your cases loads into that dataset, so the Studio cannot open on it.",
  casesUnreadable:
    "Your cases could not be read just now, so the Studio cannot say which dataset it is open on. Try again in a few minutes.",
  pipelinesUnreadable: "The pipelines could not be read just now. Try again in a few minutes.",
  rightsUnreadable: "Your rights could not be read just now, so every action is offered and the service decides.",
  working: (caseName: string, datasetName: string) =>
    `Working through the case “${caseName}”: what loads here goes into ${datasetName}.`,
  stripLabel: "Where this dataset stands",
  placesLabel: "Ingest Studio places",
  needsYouCame: (proposed: number, datasetName: string) =>
    proposed > 0
      ? `Needs you sent you here: ${plural(proposed, "proposed link type", "proposed link types")} to decide in ${datasetName}. They are on 1 Model.`
      : `Needs you sent you here: the proposed link types of ${datasetName} are on 1 Model.`,
  help: {
    title: "Roles, teams and Authors",
    intro:
      "What you can do in the Ingest Studio depends on the rights your roles give you. An administrator gives roles and teams; the Studio says which right an action needs when you do not hold it.",
    roles: "Your roles",
    rights: "Your rights",
    nothing: "none",
    rolesUnreadable: "Your roles could not be read just now.",
  },
} as const;

/** The places in order, with the labels the screens use. A place with no `path` is not on the pages yet. */
export const PLACES: readonly { id: StudioPlace; label: string; path: string | null }[] = [
  { id: "model", label: "1 Model", path: null },
  { id: "sources", label: "2 Sources", path: null },
  { id: "pipelines", label: "3 Pipelines", path: null },
  { id: "runs", label: "4 Runs", path: null },
  { id: "releases", label: "5 Releases", path: "/studio/releases" },
];

/** The Needs-you words the Studio uses (`packages/glass-shared/src/admin/needsYou/needsYouApi.ts`, `NEEDS_YOU_WORDS`). */
export const NEEDS_YOU_WORDS = {
  reminder: (n: number) => `${plural(n, "proposed link type waits", "proposed link types wait")} for you on the Model tab.`,
  reminderTip:
    "Analysts proposed new link types for this dataset. Decide them on 1 Model: added to the draft model, a type is made live with the next model version.",
  unreadProposals: "The proposed link types waiting for you could not be counted; the Model tab lists them.",
} as const;

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Where a place not yet on the pages opens: the Studio in the workspace, on the same case. */
export function workspaceStudioHref(caseId: string): string {
  return `/?investigation=${encodeURIComponent(caseId)}&from=case&view=ingest`;
}

/** The address of a place, for a case. */
export function placeHref(place: { path: string | null }, caseId: string): string {
  return place.path === null ? workspaceStudioHref(caseId) : `${place.path}?case=${encodeURIComponent(caseId)}`;
}

// -------------------------------------------------------------------------------------------- datasets and the case

/** Every dataset one of the person's cases loads into (its first), once each, the current case's first. */
export function studioDatasets(cases: readonly CaseListing[], currentId: string | null): StudioDataset[] {
  const ordered = [...cases.filter((c) => c.id === currentId), ...cases.filter((c) => c.id !== currentId)];
  const seen = new Map<string, StudioDataset>();
  for (const listing of ordered) {
    const id = listing.dataset_ids?.[0];
    if (id && !seen.has(id)) seen.set(id, { id, name: listing.datasets?.[0] ?? id });
  }
  return [...seen.values()];
}

/** The dataset the Studio is open on: its case's first. `null` when the case reads none or is not the person's. */
export function currentDataset(cases: readonly CaseListing[], caseId: string | null): string | null {
  return cases.find((c) => c.id === caseId)?.dataset_ids?.[0] ?? null;
}

const LEVEL_ORDER: Record<AccessLevel, number> = { author: 0, editor: 1, viewer: 2 };

/** The case the Studio works through for a dataset: the current case when it loads into it, else a case of the person's whose first dataset it is (the higher level first). */
export function caseForDataset(cases: readonly CaseListing[], datasetId: string, currentId: string | null): string | null {
  if (currentDataset(cases, currentId) === datasetId) return currentId;
  const byRank = (a: CaseListing, b: CaseListing): number =>
    LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level] || a.name.localeCompare(b.name);
  const loadsInto = cases.filter((c) => c.dataset_ids?.[0] === datasetId).sort(byRank);
  return loadsInto[0]?.id ?? null;
}

const PACKS: readonly { name: string; label: string }[] = [
  { name: "fibo", label: "Financial fraud and AML (FIBO)" },
  { name: "niem", label: "Crime case analysis (NIEM)" },
  { name: "stix", label: "Cyber threat analytics (STIX 2.1)" },
];

/** The domain model in words: the POLE core, then each pack the case carries, in the catalogue's order. */
export function modelInWords(packs: readonly string[] | undefined): string {
  const named = PACKS.filter((p) => (packs ?? []).includes(p.name)).map((p) => p.label);
  return ["POLE core", ...named].join(" + ");
}

// ------------------------------------------------------------------------------------------------ the readiness strip

export interface Pipeline {
  recipe_id?: string;
  status?: string;
  source_location?: string | null;
  verified_at?: string | null;
}

export interface Run {
  started_at: string;
  outcome: string;
}

export interface Source {
  location?: string;
}

export function isDeployed(p: Pipeline): boolean {
  return p.status === "published" || p.status === "flagged";
}

export function isUntested(p: Pipeline): boolean {
  return p.status === "draft" && !p.verified_at;
}

export function sourcesInWords(sources: readonly Source[] | "unreadable", pipelines: readonly Pipeline[]): string {
  if (sources === "unreadable") return "sources could not be read";
  const registered = new Set(sources.map((s) => s.location));
  const read = [...new Set(pipelines.map((p) => p.source_location).filter((s): s is string => !!s))];
  const loose = read.filter((f) => !registered.has(f)).length;
  const count = `${sources.length} ${sources.length === 1 ? "source" : "sources"}`;
  return loose ? `${count} · ${loose} ${loose === 1 ? "file" : "files"} not registered` : count;
}

export function lastRunInWords(runs: Record<string, readonly Run[]>): string {
  const all = Object.values(runs).flat();
  const last = all.reduce<Run | null>((latest, r) => (!latest || r.started_at > latest.started_at ? r : latest), null);
  if (!last) return "no run yet";
  const at = new Date(last.started_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });
  return `last run ${at} UTC, ${last.outcome}`;
}

/** The strip's items, in words. */
export function stripItems(input: {
  packs: readonly string[] | undefined;
  pipelines: readonly Pipeline[] | "unreadable";
  sources: readonly Source[] | "unreadable";
  runs: Record<string, readonly Run[]>;
}): string[] {
  const list = input.pipelines === "unreadable" ? [] : input.pipelines;
  const untested = list.filter(isUntested).length;
  return [
    `Model: ${modelInWords(input.packs)}`,
    sourcesInWords(input.sources, list),
    input.pipelines === "unreadable"
      ? "pipelines could not be read"
      : `${list.length} ${list.length === 1 ? "pipeline" : "pipelines"}${untested ? ` · ${untested} untested` : ""}`,
    lastRunInWords(input.runs),
  ];
}

// -------------------------------------------------------------------------------------------------- the rights gate

/** The screens' name for a right: `edit_target_model` is "Edit domain model"; any other is its words capitalised. */
const RIGHT_NAMES: Record<string, string> = { edit_target_model: "Edit domain model" };

export function rightName(right: string): string {
  const named = RIGHT_NAMES[right];
  if (named) return named;
  const words = right.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Why a person cannot take an action needing every one of `needs`, or `null` when they can (or when their rights are not
 * known: the action is then offered, and the Conduit answers for itself). The right's name only: the roles that hold a right
 * are not in any answer the Conduit gives a person (`GET /v1/me` has their own roles, `GET /v1/me/rights` their rights), and
 * the table that names them is the workspace's (`help/roles.ts`) until it moves to the shared package. This is words, not
 * access control: the Conduit refuses all the same (rule 3).
 */
export function whyNot(held: ReadonlySet<string> | null, needs: readonly string[]): string | null {
  if (held === null) return null;
  const missing = needs.find((right) => !held.has(right));
  return missing === undefined ? null : `You need ${rightName(missing)}. Ask an administrator to give it to you.`;
}

// ------------------------------------------------------------------------------------------------------- Releases

export const RELEASE_WORDS = {
  noDataset: "This case loads into no dataset, so there is nothing to release.",
  intro:
    "A release carries this dataset's domain model, its published pipelines and its reference lists' definitions to another environment, as YAML. It never carries a credential, loaded data, case membership, an owner, or a licensed screening list's rows.",
  noExport: "Exporting needs Edit domain model and Publish pipelines.",
  noImport: "Importing needs Edit domain model and Edit pipelines.",
  drafts: "Everything imported is a draft. Make the model live in 1 Model when it is ready.",
  checkFirst: "Check the folder first: the import is offered once the check finds nothing wrong.",
  replaceOwn: "Replace my draft of the domain model",
  replaceOwnHint:
    "You have a draft of this dataset's domain model open. Importing replaces it, and what you have not made live in 1 Model is lost.",
  chooseFolder: "Choose the release's folder first.",
  gone: "That folder is no longer held. Choose the folder again.",
  badName: "A file in the folder has a name a release cannot use.",
  notInRelease: "That file is not in the release.",
  tooLarge: "That folder is larger than the Studio holds for a check (2 MB).",
  tooMany: "That folder has more files than the Studio holds for a check (200).",
  sessionEnding: "Your sign-in is about to end, so the folder could not be held. Sign in again and choose the folder again.",
  folderRead: (n: number) => `Read ${n} ${n === 1 ? "file" : "files"} from the folder.`,
  exported: (n: number) => `The release has ${n} ${n === 1 ? "file" : "files"}.`,
  leftOut: (n: number) => ` ${n} published pipeline(s) are marked above what you may view, so they are not in it.`,
  cliHint: (datasetId: string, name: string, version: string) =>
    `To keep the files as a folder, run: ospreyflow release export ${datasetId} --name ${name} --release-version ${version} --out <folder>`,
  missingConnection: (name: string) =>
    `This environment has no connection named “${name}”: add one in Admin › Connections before a run.`,
  note: (note: string) => `Note: ${note}.`,
} as const;

export const ACTION_WORDS: Record<string, string> = {
  new_draft: "a new draft",
  replaces_draft: "the draft, in place of the one open now",
};

/** A release's name as Kubernetes takes one: lower case, digits, '-' and '.'. */
export function releaseName(datasetName: string): string {
  const slug = datasetName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 60) || "release";
}

export interface Plan {
  dry_run?: boolean;
  items?: { role?: string; name: string; action: string }[];
  refused?: string[];
  missing_connections?: string[];
  notes?: string[];
  replaces_own_draft?: boolean;
  own_draft_version?: number;
}

export interface PlanView {
  refused: string[];
  lines: string[];
  captions: string[];
}

/** The plan in words: what would be (or was) written, and the connection and notes lines. */
export function planView(plan: Plan, dryRun: boolean): PlanView {
  return {
    refused: plan.refused ?? [],
    lines: (plan.items ?? []).map(
      (item) => `${dryRun ? "Would write" : "Wrote"} ${item.name} as ${ACTION_WORDS[item.action] ?? "a draft"}.`,
    ),
    captions: [
      ...(plan.missing_connections ?? []).map((name) => RELEASE_WORDS.missingConnection(name)),
      ...(plan.notes ?? []).map((note) => RELEASE_WORDS.note(note)),
    ],
  };
}

/**
 * A refusal in words. The same words for a dataset that is not the person's and a right they do not hold: the Conduit answers
 * both as a refusal, and the page must not tell them apart (rule 3: nobody learns what exists by how a refusal is worded).
 *
 * Its own `problems` and `refused` lists, which are the release's own faults, are shown as it sent them. So is a string
 * `detail` on any other refusal (4xx), as the React screen's `wordsOf` shows it: the import into a composite or a drawn dataset
 * is 409 with the reason in `detail`, a permanent refusal that must not read as a passing fault. The `detail` of a 401, a 403
 * and a 404 is never shown (the 403's names the right, and the 404's is the same as for a dataset that does not exist). Only a
 * Conduit that failed (5xx, or an answer the page could not read) is worded as a fault to try again; a 4xx never is.
 */
export function refusalWords(status: number, body: unknown, what: string): string {
  if (status === 401) return "Your session has ended, or your access could not be checked. Sign in again.";
  if (status === 403 || status === 404) {
    return `${what} is not available to you: it needs rights you do not hold, or the dataset is not one of yours.`;
  }
  const said = body as { problems?: unknown; refused?: unknown; detail?: unknown } | undefined;
  for (const list of [said?.problems, said?.refused]) {
    if (Array.isArray(list) && list.length > 0 && list.every((line) => typeof line === "string")) return (list as string[]).join("; ");
  }
  if (status >= 400 && status < 500) {
    return typeof said?.detail === "string" && said.detail.trim() !== "" ? said.detail : `${what} was refused (${status}).`;
  }
  return `${what} could not be carried out just now. Nothing was changed. Try again in a few minutes.`;
}

/** The path inside the release for a file a folder sent: the folder's own name taken off, as `bundleFromFolder` does. Null for a name a release cannot use. */
export function bundlePath(filename: string): string | null {
  if (filename === "" || filename.length > 255 || /[\u0000-\u001f\u007f\\]/.test(filename)) return null;
  const parts = filename.split("/");
  const inside = parts.length > 1 ? parts.slice(1) : parts;
  if (inside.some((part) => part === "" || part === "." || part === "..")) return null;
  if (parts.length > 1 && parts[0] === "") return null;
  return inside.join("/");
}

/** A download's file name: the path with each slash made `__`, and only plain characters kept. */
export function downloadName(path: string): string {
  return path.replace(/\//g, "__").replace(/[^A-Za-z0-9._-]/g, "_");
}
