// Studio › Releases' calls (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4): the dataset's release
// exported as its YAML bundle's files, and a bundle imported as drafts (with a dry run first).
// `ospreyflow release export|import` call the same two routes (`cli/ospreyflow/conduit_client.py`).
import type {
  ReleaseExport,
  ReleaseImportPlan,
} from "../../../../../packages/schemas/generated";

function dataset(apiBaseUrl: string, datasetId: string): string {
  return `${apiBaseUrl}/v1/datasets/${encodeURIComponent(datasetId)}`;
}

/** The refusal's own words (`problems`, `refused`, `detail`), never a status code alone. */
async function wordsOf(response: Response, what: string): Promise<string> {
  try {
    const body = (await response.json()) as {
      problems?: string[];
      refused?: string[];
      detail?: unknown;
    };
    const words = body.problems ?? body.refused;
    if (words && words.length > 0) return words.join("; ");
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // no body: say what was refused
  }
  if (response.status === 403) return `${what} needs rights you do not hold.`;
  return `${what} was refused (${response.status}).`;
}

export async function exportRelease(
  apiBaseUrl: string,
  bearerToken: string,
  datasetId: string,
  name: string,
  version: string,
): Promise<ReleaseExport> {
  const query = new URLSearchParams({ name, version });
  const response = await fetch(
    `${dataset(apiBaseUrl, datasetId)}/release?${query}`,
    {
      headers: { Authorization: `Bearer ${bearerToken}` },
    },
  );
  if (!response.ok) throw new Error(await wordsOf(response, "The export"));
  return (await response.json()) as ReleaseExport;
}

/** The import's plan. A refusal comes back as a plan too (422), with `refused` in words.
 * `replaceOwnDraft`: the importer's confirmation that their own in-progress draft of the model is
 * replaced (CARRIES row 90); another person's draft is refused whatever it says. */
export async function importRelease(
  apiBaseUrl: string,
  bearerToken: string,
  datasetId: string,
  files: Record<string, string>,
  dryRun: boolean,
  replaceOwnDraft = false,
): Promise<ReleaseImportPlan> {
  const response = await fetch(
    `${dataset(apiBaseUrl, datasetId)}/release/import?dry_run=${dryRun}&replace_own_draft=${replaceOwnDraft}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ files }),
    },
  );
  if (response.ok || response.status === 422) {
    const plan = (await response.json()) as ReleaseImportPlan;
    if (Array.isArray(plan.refused)) return plan;
  }
  throw new Error(await wordsOf(response, "The import"));
}

/** A release's name as Kubernetes takes one: lower case, digits, '-' and '.'. */
export function releaseName(datasetName: string): string {
  const slug = datasetName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 60) || "release";
}

/** The bundle's files from a chosen folder: each path below the folder, as the export wrote it. */
export async function bundleFromFolder(
  files: readonly File[],
): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  for (const file of files) {
    const relative =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
      file.name;
    const parts = relative.split("/");
    const path =
      parts.length > 1 ? parts.slice(1).join("/") : (parts[0] ?? file.name);
    out[path] = await file.text();
  }
  return out;
}
